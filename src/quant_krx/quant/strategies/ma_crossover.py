from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import vectorbt as vbt

from quant_krx.quant.base import BacktestResult
from quant_krx.quant.metrics import extract_metrics


@dataclass
class MACrossoverStrategy:
    name: str = "ma_crossover"
    display_name: str = "이동평균 교차 (20/60일)"
    short_window: int = 20
    long_window: int = 60

    @property
    def params(self) -> dict[str, Any]:
        return {"short_window": self.short_window, "long_window": self.long_window}

    def run(
        self,
        ohlcv: pd.DataFrame,
        benchmark: pd.DataFrame | None,
        fees: float = 0.003,
        slippage: float = 0.001,
        run_id: str = "",
    ) -> BacktestResult:
        close = (
            ohlcv.set_index("date")["close"]
            if "date" in ohlcv.columns
            else ohlcv["close"]
        )
        close.index = pd.to_datetime(close.index)
        close = close.astype(float).sort_index()

        short_ma = close.rolling(self.short_window).mean()
        long_ma = close.rolling(self.long_window).mean()

        entries = (short_ma > long_ma) & (short_ma.shift(1) <= long_ma.shift(1))
        exits = (short_ma < long_ma) & (short_ma.shift(1) >= long_ma.shift(1))

        pf = vbt.Portfolio.from_signals(
            close,
            entries,
            exits,
            fees=fees,
            slippage=slippage,
            freq="D",
        )

        symbol = ohlcv["symbol"].iloc[0] if "symbol" in ohlcv.columns else "UNKNOWN"
        metrics = extract_metrics(pf, close, benchmark, fees, slippage)
        trades_df = (
            pf.trades.records_readable
            if hasattr(pf.trades, "records_readable")
            else pd.DataFrame()
        )
        equity = pf.value()

        return BacktestResult(
            symbol=symbol,
            strategy_name=self.name,
            strategy_display_name=self.display_name,
            params=self.params,
            start=close.index[0].date(),
            end=close.index[-1].date(),
            metrics=metrics,
            trades=trades_df,
            equity_curve=equity,
            run_id=run_id,
        )
