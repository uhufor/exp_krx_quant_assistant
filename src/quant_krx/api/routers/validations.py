from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from quant_krx.api.deps import get_db, get_workspace_service
from quant_krx.api.errors import NotFoundError
from quant_krx.screening.service import ScreeningService
from quant_krx.storage.db import Database
from quant_krx.workspace.data_loading import (
    _ohlcv_provider_for,
    prepare_backtest_data,
    prepare_dynamic_universe,
    resolve_backtest_symbols,
)
from quant_krx.workspace.errors import WorkspaceError, not_found_hint
from quant_krx.workspace.serialization import serialize_equity_curve, serialize_metrics
from quant_krx.workspace.service import WorkspaceService
from quant_krx.workspace.validation import ValidationReport, ValidationSpec
from quant_krx.workspace.walkforward import FoldSpecError

router = APIRouter()
logger = logging.getLogger(__name__)


class ValidationRequest(BaseModel):
    """백테스트 요청과 같은 규약 + 검증 스펙. 기본값도 CLI와 일치시킨다."""

    strategy_id: str
    symbols: list[str] | None = None
    start: date | None = None
    end: date | None = None
    data_source: Literal["fixture", "krx_dart"] = "fixture"
    fees: float = 0.003
    slippage: float = 0.001
    benchmark: str | None = None
    mode: Literal["holdout", "walkforward"] = "walkforward"
    n_folds: int = 3
    test_ratio: float = 0.3
    anchored: bool = True
    objective: Literal["sharpe", "total_return", "calmar"] = "sharpe"
    grid: dict[str, list[Any]] = {}


def _default_dates(end: date | None, start: date | None) -> tuple[date, date]:
    end_date = end or date.today()
    start_date = start or date(end_date.year - 5, end_date.month, end_date.day)
    return start_date, end_date


@router.post("")
def run_validation(
    body: ValidationRequest,
    db: Database = Depends(get_db),
    svc: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """OOS/워크포워드 검증 실행(P4).

    동기 def 핸들러(FastAPI 스레드풀 실행) — (그리드 × 폴드)만큼 백테스트를 돌리므로
    백테스트보다도 오래 걸린다. event loop를 블로킹하지 않는다.
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

    def _warn(label: str, exc: Exception) -> None:
        logger.warning("검증 데이터 준비 경고(%s, 건너뛰고 계속): %s", label, exc)

    data, benchmark_df = prepare_backtest_data(
        db, defn, sym_list,
        data_source=body.data_source, start=start_date, end=end_date, benchmark=body.benchmark,
        resolve_rule=svc.get_rule, resolve_formula=svc.get_formula,
        on_benchmark_warning=_warn,
        on_symbol_error=_warn,
        on_fundamental_warning=_warn,
    )
    if not data:
        raise NotFoundError("모든 종목의 데이터 조립이 실패했습니다")

    spec = ValidationSpec(
        mode=body.mode, n_folds=body.n_folds, test_ratio=body.test_ratio,
        anchored=body.anchored, objective=body.objective, grid=body.grid,
    )
    try:
        report = svc.validate_oos(  # WorkspaceError -> 409(api/errors.py)
            body.strategy_id, data=data, spec=spec, start=start_date, end=end_date,
            fees=body.fees, slippage=body.slippage, benchmark=benchmark_df,
            data_source=body.data_source, benchmark_symbol=body.benchmark,
            resolve_universe=universe_plan.eligible_at if universe_plan else None,
        )
    except FoldSpecError as e:
        # 폴드 분할 실패는 사용자 입력 문제이므로 500이 아니라 409로 돌려준다.
        raise WorkspaceError(str(e)) from e
    return serialize_validation_report(report)


@router.get("")
def list_validation_runs(
    strategy_id: str | None = None,
    limit: int = 50,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> list[dict[str, Any]]:
    """저장된 검증 이력 목록(최근순). 폴드 상세·곡선은 제외해 응답이 비대해지지 않게 한다."""
    return [
        {
            "validation_id": r["validation_id"],
            "strategy_id": r["strategy_id"],
            "spec": r["spec"],
            "params": r["params"],
            "summary": r["summary"],
            "executed_at": r["executed_at"].isoformat(),
        }
        for r in svc.list_validation_runs(strategy_id=strategy_id, limit=limit)
    ]


@router.get("/{validation_id}")
def get_validation_run(
    validation_id: str,
    svc: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    report = svc.get_validation_run(validation_id)
    if report is None:
        raise NotFoundError(f"검증 실행 '{validation_id}'을(를) 찾을 수 없습니다")
    record = svc.get_validation_run_record(validation_id)
    return {**serialize_validation_report(report), "params": record["params"]}


def serialize_validation_report(report: ValidationReport) -> dict[str, Any]:
    """검증 리포트 -> GUI 응답. 저장 포맷과 같은 직렬화 계약을 쓴다(serialization.py)."""
    return {
        "validation_id": report.validation_id,
        "strategy_id": report.strategy_id,
        "spec": report.spec.to_dict(),
        "summary": report.summary.to_dict(),
        "oos_equity": serialize_equity_curve(report.oos_equity),
        "executed_at": report.executed_at.isoformat() if report.executed_at else None,
        "folds": [
            {
                "fold": f.fold.to_dict(),
                "params": dict(f.params),
                "train_metrics": (
                    serialize_metrics(f.train_metrics) if f.train_metrics is not None else None
                ),
                "test_metrics": (
                    serialize_metrics(f.test_metrics) if f.test_metrics is not None else None
                ),
                "candidates": [c.to_dict() for c in f.candidates],
                "error": f.error,
            }
            for f in report.folds
        ],
    }
