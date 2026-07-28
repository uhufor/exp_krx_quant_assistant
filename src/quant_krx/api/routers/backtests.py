from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from quant_krx.api.deps import get_db, get_workspace_service
from quant_krx.api.errors import NotFoundError
from quant_krx.api.schemas.backtest import serialize_backtest_report
from quant_krx.screening.service import ScreeningService
from quant_krx.storage.db import Database
from quant_krx.workspace.data_loading import (
    _ohlcv_provider_for,
    prepare_backtest_data,
    prepare_dynamic_universe,
    resolve_backtest_symbols,
)
from quant_krx.workspace.errors import not_found_hint
from quant_krx.workspace.service import WorkspaceService

router = APIRouter()
logger = logging.getLogger(__name__)


class BacktestRequest(BaseModel):
    strategy_id: str
    symbols: list[str] | None = None  # 생략 시 전략 universe.symbols 사용(CLI와 동일 규약)
    start: date | None = None  # 생략 시 종료일 5년 전(CLI와 동일 규약)
    end: date | None = None  # 생략 시 오늘
    data_source: Literal["fixture", "fixture_10y", "krx_dart"] = "fixture"
    fees: float = 0.003
    slippage: float = 0.001
    benchmark: str | None = None
    use_cache: bool = True  # False면 동일 조건의 저장된 결과를 무시하고 재계산(P3)


def _default_dates(end: date | None, start: date | None) -> tuple[date, date]:
    end_date = end or date.today()
    start_date = start or date(end_date.year - 5, end_date.month, end_date.day)
    return start_date, end_date


@router.post("")
def run_backtest(
    body: BacktestRequest,
    db: Database = Depends(get_db),
    svc: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """PRD 백테스트 AC1-4 — prepare_backtest_data(TR-GUI-003) + svc.backtest()를 그대로 재사용.

    동기 def 핸들러(FastAPI 스레드풀 실행) — pykrx 수집이 수 분 걸릴 수 있어 event loop를
    블로킹하지 않는다(TR-GUI-010).
    """
    defn = svc.get_strategy(body.strategy_id)
    if defn is None:
        hint = not_found_hint(d.id for d in svc.list_strategies())
        raise NotFoundError(f"전략 '{body.strategy_id}'을(를) 찾을 수 없습니다.{hint}")

    start_date, end_date = _default_dates(body.end, body.start)

    universe_plan = None
    if defn.universe.is_dynamic and not body.symbols:
        screening_svc = ScreeningService(db, _ohlcv_provider_for(body.data_source))
        universe_plan = prepare_dynamic_universe(
            defn, start=start_date, end=end_date,
            resolve=lambda condition_id, as_of: screening_svc.resolve_symbols(
                condition_id, as_of
            ),
        )
        sym_list = universe_plan.symbols
    else:
        sym_list = resolve_backtest_symbols(defn, body.symbols)

    if not sym_list:
        raise NotFoundError(
            "대상 종목이 없습니다. symbols 지정 또는 전략 universe 설정 필요"
            "(동적 유니버스라면 어느 시점에도 통과 종목이 없었습니다)"
        )

    def _warn_benchmark_failure(bm: str, exc: Exception) -> None:
        logger.warning("벤치마크 '%s' 수집 실패(무시하고 계속): %s", bm, exc)

    data_errors: dict[str, str] = {}

    def _warn_symbol_failure(sym: str, exc: Exception) -> None:
        data_errors[sym] = str(exc)
        logger.warning("종목 '%s' 데이터 조립 실패(건너뛰고 계속): %s", sym, exc)

    def _warn_fundamental_failure(label: str, exc: Exception) -> None:
        logger.warning("펀더멘털 수집 실패(%s, 건너뛰고 계속): %s", label, exc)

    data, benchmark_df = prepare_backtest_data(
        db, defn, sym_list,
        data_source=body.data_source, start=start_date, end=end_date, benchmark=body.benchmark,
        resolve_rule=svc.get_rule, resolve_formula=svc.get_formula,
        on_benchmark_warning=_warn_benchmark_failure,
        on_symbol_error=_warn_symbol_failure,
        on_fundamental_warning=_warn_fundamental_failure,
    )
    if not data:
        detail = "; ".join(f"{s}: {m}" for s, m in data_errors.items())
        raise NotFoundError(f"모든 종목의 데이터 조립이 실패했습니다({detail})")

    report = svc.backtest(  # runnable/검증 실패 -> WorkspaceError -> 409(api/errors.py)
        body.strategy_id, data=data, start=start_date, end=end_date,
        fees=body.fees, slippage=body.slippage, benchmark=benchmark_df,
        data_source=body.data_source, benchmark_symbol=body.benchmark,
        use_cache=body.use_cache,
        resolve_universe=universe_plan.eligible_at if universe_plan else None,
    )
    result = serialize_backtest_report(report)
    result["errors"] = {**data_errors, **result["errors"]}
    return result


@router.get("/runs")
def list_backtest_runs(
    strategy_id: str | None = None,
    limit: int = 50,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> list[dict[str, Any]]:
    """저장된 백테스트 실행 이력 목록(최근순, P3)."""
    return [_serialize_run_summary(r) for r in svc.list_backtest_runs(
        strategy_id=strategy_id, limit=limit
    )]


@router.get("/runs/{run_id}")
def get_backtest_run(
    run_id: str,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """저장된 실행 1건 — 실행 파라미터 + 지표 + 자본곡선(거래내역은 미저장)."""
    record = svc.get_backtest_run_record(run_id)
    if record is None:
        raise NotFoundError(f"백테스트 실행 '{run_id}'을(를) 찾을 수 없습니다")
    return {**_serialize_run_summary(record), "equity_curves": record["equity_curves"]}


def _serialize_run_summary(record: dict[str, Any]) -> dict[str, Any]:
    """equity_curves를 제외한 실행 요약 — 목록 응답이 곡선 데이터로 비대해지지 않게 한다."""
    return {
        "run_id": record["run_id"],
        "strategy_id": record["strategy_id"],
        "params": record["params"],
        "metrics": record["metrics"],
        "per_symbol": record["per_symbol"],
        "benchmark": record["benchmark"],
        "benchmark_note": record["benchmark_note"],
        "errors": record["errors"],
        "definition_hash": record["definition_hash"],
        "coverage_fingerprint": record["coverage_fingerprint"],
        "executed_at": record["executed_at"].isoformat(),
        "is_portfolio": record["is_portfolio"],
        "weights": record["weights"],
    }
