from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import vectorbt as vbt

from quant_krx.quant.base import BacktestResult
from quant_krx.quant.metrics import extract_metrics


@dataclass
class MomentumStrategy:
    """12-1 가격 모멘텀 전략.

    Jegadeesh & Titman(1993)이 검증한 모멘텀 팩터.
    12개월 전 ~ 1개월 전 구간의 수익률이 양수로 전환되면 매수,
    음수로 전환되면 매도. 중장기 추세 지속성을 활용.
    """

    name: str = "momentum"
    lookback_days: int = 252   # 12개월 (약 252 거래일)
    skip_days: int = 21        # 최근 1개월 제외 (단기 반전 효과 회피)

    @property
    def params(self) -> dict[str, Any]:
        return {"lookback_days": self.lookback_days, "skip_days": self.skip_days}

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

        # 12개월 전 가격 대비 1개월 전 가격의 수익률
        momentum = close.shift(self.skip_days) / close.shift(self.lookback_days) - 1

        entries = (momentum > 0) & (momentum.shift(1) <= 0)
        exits = (momentum < 0) & (momentum.shift(1) >= 0)

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
