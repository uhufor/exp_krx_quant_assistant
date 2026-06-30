from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import vectorbt as vbt

from quant_krx.quant.base import BacktestResult
from quant_krx.quant.metrics import extract_metrics


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


@dataclass
class RSIBreakoutStrategy:
    name: str = "rsi_breakout"
    rsi_window: int = 14
    oversold: float = 30.0
    overbought: float = 70.0

    @property
    def params(self) -> dict[str, Any]:
        return {
            "rsi_window": self.rsi_window,
            "oversold": self.oversold,
            "overbought": self.overbought,
        }

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

        rsi = _rsi(close, self.rsi_window)

        entries = rsi < self.oversold
        exits = rsi > self.overbought

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
            params=self.params,
            start=close.index[0].date(),
            end=close.index[-1].date(),
            metrics=metrics,
            trades=trades_df,
            equity_curve=equity,
            run_id=run_id,
        )
