from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import vectorbt as vbt

from quant_krx.quant.base import BacktestResult
from quant_krx.quant.metrics import extract_metrics


@dataclass
class BollingerBandStrategy:
    """볼린저 밴드 평균 회귀 전략.

    가격이 하단 밴드(MA - n*σ) 아래로 내려가면 과매도로 보고 매수,
    상단 밴드(MA + n*σ) 위로 올라가면 과매수로 보고 매도.
    """

    name: str = "bollinger_band"
    display_name: str = "볼린저 밴드"
    window: int = 20
    num_std: float = 2.0

    @property
    def params(self) -> dict[str, Any]:
        return {"window": self.window, "num_std": self.num_std}

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

        ma = close.rolling(self.window).mean()
        std = close.rolling(self.window).std()
        lower = ma - self.num_std * std
        upper = ma + self.num_std * std

        entries = (close < lower) & (close.shift(1) >= lower.shift(1))
        exits = (close > upper) & (close.shift(1) <= upper.shift(1))

        pf = vbt.Portfolio.from_signals(
            close, entries, exits,
            fees=fees, slippage=slippage, freq="D",
        )

        metrics = extract_metrics(pf, close, benchmark, fees, slippage)
        trades_df = (
            pf.trades.records_readable
            if hasattr(pf.trades, "records_readable")
            else pd.DataFrame()
        )

        return BacktestResult(
            symbol="UNKNOWN",
            strategy_name=self.name,
            strategy_display_name=self.display_name,
            params=self.params,
            start=close.index[0].date(),
            end=close.index[-1].date(),
            metrics=metrics,
            trades=trades_df,
            equity_curve=pf.value(),
            run_id=run_id,
        )
