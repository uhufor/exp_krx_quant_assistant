from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

# 직렬화 계약의 진실 원천은 workspace/serialization.py — 저장된 실행 이력(P3)과 GUI 응답이
# 동일 포맷이어야 하므로 한 곳에 두고 여기서 재export한다(기존 import 경로 유지).
from quant_krx.workspace.serialization import (
    serialize_equity_curve,
    serialize_metrics,
)
from quant_krx.workspace.serialization import (
    to_json_safe as _to_json_safe,
)

if TYPE_CHECKING:
    from quant_krx.quant.base import BacktestResult as QuantBacktestResult
    from quant_krx.workspace.backtest import BacktestReport

__all__ = [
    "serialize_backtest_report",
    "serialize_equity_curve",
    "serialize_metrics",
    "serialize_trades",
]


def _normalize_column(col: str) -> str:
    return col.strip().lower().replace(" ", "_")


def serialize_trades(df: pd.DataFrame) -> list[dict[str, Any]]:
    """vectorbt records_readable DataFrame -> snake_case 컬럼 JSON 레코드 목록.

    컬럼명은 vectorbt 라이브러리가 정하며 이 코드베이스가 통제하지 않으므로, 정확한
    이름을 하드코딩하지 않고 일괄 snake_case 정규화한다(TRD-R01 §5.1: 이 GUI가 최초
    소비자이므로 계약을 자유롭게 정의).
    """
    if df.empty:
        return []
    renamed = df.rename(columns=_normalize_column)
    return [
        {k: _to_json_safe(v) for k, v in record.items()}
        for record in renamed.to_dict("records")
    ]


def serialize_backtest_report(report: BacktestReport) -> dict[str, Any]:
    return {
        "metrics": serialize_metrics(report.metrics),
        "per_symbol": {sym: serialize_metrics(m) for sym, m in report.per_symbol.items()},
        "results": {
            sym: _serialize_result(result) for sym, result in report.results.items()
        },
        "benchmark": report.benchmark,
        "benchmark_note": report.benchmark_note,
        "errors": report.errors,
        # 실행 이력(P3) — from_cache=True면 저장된 결과 복원이라 results[*].trades가 비어 있다.
        "run_id": report.run_id,
        "executed_at": report.executed_at.isoformat() if report.executed_at else None,
        "from_cache": report.from_cache,
        # 포트폴리오 모드(P1) — True면 results 키가 "__portfolio__" 하나뿐이고
        # per_symbol은 비어 있다(자본 공유라 종목별 독립 성과가 정의되지 않음).
        "is_portfolio": report.is_portfolio,
        "weights": report.weights,
    }


def _serialize_result(result: QuantBacktestResult) -> dict[str, Any]:
    return {
        "equity_curve": serialize_equity_curve(result.equity_curve),
        "price_curve": serialize_equity_curve(result.price),
        "trades": serialize_trades(result.trades),
    }
