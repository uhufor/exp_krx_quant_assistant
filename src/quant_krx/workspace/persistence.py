"""백테스트 실행 이력의 영속·복원(P3).

저장 범위는 **메트릭 + 자본곡선/주가곡선**이다. 거래내역(trades)은 재실행으로 재생성
가능하고 용량이 커서 저장하지 않는다 — 따라서 캐시로 복원한 리포트의
`BacktestResult.trades`는 항상 빈 DataFrame이며, 이를 소비자가 구분할 수 있도록
`BacktestReport.from_cache`가 True로 설정된다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from quant_krx.quant.base import BacktestResult as QuantBacktestResult
from quant_krx.workspace.backtest import BacktestReport
from quant_krx.workspace.serialization import (
    deserialize_equity_curve,
    deserialize_metrics,
    serialize_equity_curve,
    serialize_metrics,
)


def serialize_curves(report: BacktestReport) -> dict[str, dict[str, Any]]:
    return {
        symbol: {
            "equity": serialize_equity_curve(result.equity_curve),
            "price": serialize_equity_curve(result.price),
        }
        for symbol, result in report.results.items()
    }


def build_run_record(
    report: BacktestReport,
    *,
    run_id: str,
    cache_key: str,
    strategy_id: str,
    definition_hash: str,
    coverage_fingerprint: str,
    params: dict[str, Any],
    executed_at: datetime,
) -> dict[str, Any]:
    """BacktestReport -> backtest_runs 행 딕셔너리(Database.insert_backtest_run 입력)."""
    return {
        "run_id": run_id,
        "cache_key": cache_key,
        "strategy_id": strategy_id,
        "definition_hash": definition_hash,
        "coverage_fingerprint": coverage_fingerprint,
        "params": params,
        "metrics": serialize_metrics(report.metrics),
        "per_symbol": {sym: serialize_metrics(m) for sym, m in report.per_symbol.items()},
        "equity_curves": serialize_curves(report),
        "benchmark": report.benchmark,
        "benchmark_note": report.benchmark_note,
        "errors": dict(report.errors),
        "executed_at": executed_at,
        "is_portfolio": report.is_portfolio,
        "weights": dict(report.weights),
    }


def _parse_date(value: Any) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def restore_report(record: dict[str, Any]) -> BacktestReport:
    """backtest_runs 행 -> BacktestReport 복원(trades는 빈 DataFrame, from_cache=True).

    소비자(CLI 표·GUI)가 캐시 히트와 신규 실행을 분기 없이 다룰 수 있도록 동일한
    `BacktestReport` 타입으로 되돌린다.
    """
    params = record.get("params") or {}
    start = _parse_date(params.get("start"))
    end = _parse_date(params.get("end"))
    per_symbol = {sym: deserialize_metrics(m) for sym, m in record["per_symbol"].items()}

    results: dict[str, QuantBacktestResult] = {}
    for symbol, curves in record["equity_curves"].items():
        results[symbol] = QuantBacktestResult(
            symbol=symbol,
            strategy_name=record["strategy_id"],
            strategy_display_name=record["strategy_id"],
            params={},
            start=start or date.min,
            end=end or date.max,
            metrics=per_symbol.get(symbol) or deserialize_metrics(record["metrics"]),
            trades=pd.DataFrame(),  # 미저장 — 재실행으로만 재생성
            equity_curve=deserialize_equity_curve(curves.get("equity", [])),
            run_id=record["run_id"],
            price=deserialize_equity_curve(curves.get("price", [])),
        )

    return BacktestReport(
        metrics=deserialize_metrics(record["metrics"]),
        per_symbol=per_symbol,
        benchmark=record.get("benchmark"),
        benchmark_note=record.get("benchmark_note"),
        results=results,
        errors=dict(record.get("errors") or {}),
        run_id=record["run_id"],
        executed_at=record["executed_at"],
        from_cache=True,
        is_portfolio=bool(record.get("is_portfolio", False)),
        weights=dict(record.get("weights") or {}),
    )
