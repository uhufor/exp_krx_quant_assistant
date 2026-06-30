from __future__ import annotations

import uuid
from datetime import datetime

import pandas as pd

from quant_krx.quant.base import BacktestResult, Strategy


class StrategyRunner:
    """전략 배치 실행기."""

    def run_one(
        self,
        strategy: Strategy,
        ohlcv: pd.DataFrame,
        benchmark: pd.DataFrame | None = None,
        fees: float = 0.003,
        slippage: float = 0.001,
        run_id: str | None = None,
    ) -> BacktestResult:
        if run_id is None:
            run_id = f"{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        return strategy.run(ohlcv, benchmark, fees, slippage, run_id)

    def run_batch(
        self,
        strategies: list[Strategy],
        ohlcv_map: dict[str, pd.DataFrame],
        benchmark: pd.DataFrame | None = None,
        fees: float = 0.003,
        slippage: float = 0.001,
        run_id: str | None = None,
    ) -> list[BacktestResult]:
        if run_id is None:
            run_id = f"{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        results = []
        for _sym, ohlcv in ohlcv_map.items():
            for strategy in strategies:
                result = strategy.run(ohlcv, benchmark, fees, slippage, run_id)
                results.append(result)
        return results
