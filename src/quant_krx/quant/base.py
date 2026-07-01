from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import pandas as pd


@dataclass
class BacktestMetrics:
    total_return: float          # 전체 수익률 (소수, 예: 0.15 = 15%)
    benchmark_return: float      # 벤치마크 수익률
    excess_return: float         # total_return - benchmark_return
    mdd: float                   # Maximum Drawdown (양수, 예: 0.25 = 25%)
    sharpe: float                # Sharpe ratio
    sortino: float               # Sortino ratio
    trade_count: int             # 총 거래 수
    fees_paid: float             # 수수료 합계
    slippage_cost: float         # 슬리피지 비용 추정
    recent_6m_return: float      # 최근 6개월 수익률
    recent_12m_return: float     # 최근 12개월 수익률
    win_rate: float              # 승률 (수익 거래 / 전체 거래)


@dataclass
class BacktestResult:
    symbol: str
    strategy_name: str
    strategy_display_name: str
    params: dict[str, Any]
    start: date
    end: date
    metrics: BacktestMetrics
    trades: pd.DataFrame         # 거래 기록
    equity_curve: pd.Series      # 자본 곡선
    run_id: str


class Strategy(Protocol):
    name: str              # 내부 식별 키 (예: "ma_crossover")
    display_name: str      # 사용자 친화적 표시 이름 (예: "이동평균 교차 (20/60일)")
    params: dict[str, Any]

    def run(
        self,
        ohlcv: pd.DataFrame,
        benchmark: pd.DataFrame | None,
        fees: float,
        slippage: float,
        run_id: str,
    ) -> BacktestResult: ...
