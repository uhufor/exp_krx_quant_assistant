from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

import pandas as pd

from quant_krx.quant.base import BacktestMetrics

if TYPE_CHECKING:
    from quant_krx.quant.base import BacktestResult as QuantBacktestResult
    from quant_krx.workspace.backtest import BacktestReport


def _to_json_safe(value: Any) -> Any:
    """pandas/numpy 스칼라를 JSON 직렬화 가능한 파이썬 네이티브 값으로 정규화.

    순서 중요: Timestamp(날짜 문자열화) -> NaN/NaT(None) -> numpy 스칼라(.item()) -> passthrough.
    """
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):  # numpy int64/float64/bool_
        return value.item()
    return value


def serialize_metrics(metrics: BacktestMetrics) -> dict[str, Any]:
    return {k: _to_json_safe(v) for k, v in dataclasses.asdict(metrics).items()}


def serialize_equity_curve(series: pd.Series) -> list[dict[str, Any]]:
    """DatetimeIndex pd.Series -> [{date, value}] (§5.1 TRD-R01 직렬화 계약)."""
    return [
        {"date": _to_json_safe(idx), "value": _to_json_safe(val)} for idx, val in series.items()
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
    }


def _serialize_result(result: QuantBacktestResult) -> dict[str, Any]:
    return {
        "equity_curve": serialize_equity_curve(result.equity_curve),
        "price_curve": serialize_equity_curve(result.price),
        "trades": serialize_trades(result.trades),
    }
