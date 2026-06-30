from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import vectorbt as vbt

from quant_krx.quant.base import BacktestResult
from quant_krx.quant.metrics import extract_metrics


@dataclass
class MACDStrategy:
    """MACD 시그널 교차 전략.

    MACD선(단기EMA - 장기EMA)이 시그널선(MACD의 EMA)을 위로 교차하면 매수,
    아래로 교차하면 매도. 커뮤니티에서 가장 널리 사용되는 모멘텀 지표.
    """

    name: str = "macd"
    fast: int = 12
    slow: int = 26
    signal: int = 9

    @property
    def params(self) -> dict[str, Any]:
        return {"fast": self.fast, "slow": self.slow, "signal": self.signal}

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

        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()

        entries = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
        exits = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))

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
            params=self.params,
            start=close.index[0].date(),
            end=close.index[-1].date(),
            metrics=metrics,
            trades=trades_df,
            equity_curve=pf.value(),
            run_id=run_id,
        )
