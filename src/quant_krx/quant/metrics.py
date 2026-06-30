from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from quant_krx.quant.base import BacktestMetrics

logger = logging.getLogger(__name__)


def extract_metrics(
    pf,  # vectorbt Portfolio
    close: pd.Series,
    benchmark: pd.DataFrame | None,
    fees: float,
    slippage: float,
) -> BacktestMetrics:
    """vectorbt Portfolio에서 BacktestMetrics 추출."""

    # 총 수익률
    total_return = float(pf.total_return())

    # MDD (max_drawdown() returns negative value)
    mdd = float(abs(pf.max_drawdown()))

    # Sharpe / Sortino (연간화)
    # trade_count=0이면 모든 수익률=0 → std=0 → inf 반환 → nan으로 처리
    try:
        sharpe = float(pf.sharpe_ratio())
        if not np.isfinite(sharpe):
            sharpe = float("nan")
    except Exception as e:
        logger.warning(f"Sharpe 추출 실패: {e}")
        sharpe = float("nan")
    try:
        sortino = float(pf.sortino_ratio())
        if not np.isfinite(sortino):
            sortino = float("nan")
    except Exception as e:
        logger.warning(f"Sortino 추출 실패: {e}")
        sortino = float("nan")

    # 거래 수
    try:
        trade_count = int(pf.trades.count())
    except Exception as e:
        logger.warning(f"trade_count 추출 실패: {e}")
        trade_count = 0

    # 수수료 합계 (entry_fees + exit_fees)
    try:
        if trade_count > 0:
            rec = pf.trades.records
            fees_paid = float(rec["entry_fees"].sum() + rec["exit_fees"].sum())
        else:
            fees_paid = 0.0
    except Exception as e:
        logger.warning(f"fees_paid 추출 실패: {e}")
        fees_paid = 0.0

    # 슬리피지 비용 추정
    slippage_cost = float(pf.init_cash * slippage * trade_count) if trade_count > 0 else 0.0

    # 승률
    try:
        win_rate = float(pf.trades.win_rate())
    except Exception as e:
        logger.warning(f"win_rate 추출 실패: {e}")
        win_rate = float("nan")

    # 벤치마크 수익률
    if benchmark is not None and not benchmark.empty:
        bm_close = (
            benchmark.set_index("date")["close"]
            if "date" in benchmark.columns
            else benchmark["close"]
        )
        bm_close = bm_close.astype(float).sort_index()
        bm_return = float((bm_close.iloc[-1] - bm_close.iloc[0]) / bm_close.iloc[0])
    else:
        bm_return = float("nan")

    excess_return = (
        total_return - bm_return
        if not (np.isnan(total_return) or np.isnan(bm_return))
        else float("nan")
    )

    # 최근 기간 수익률
    equity = pf.value()
    recent_6m = _recent_return(equity, 126)   # ~6개월 거래일
    recent_12m = _recent_return(equity, 252)  # ~12개월 거래일

    return BacktestMetrics(
        total_return=total_return,
        benchmark_return=bm_return,
        excess_return=excess_return,
        mdd=mdd,
        sharpe=sharpe,
        sortino=sortino,
        trade_count=trade_count,
        fees_paid=fees_paid,
        slippage_cost=slippage_cost,
        recent_6m_return=recent_6m,
        recent_12m_return=recent_12m,
        win_rate=win_rate,
    )


def _recent_return(equity: pd.Series, n_days: int) -> float:
    """최근 n_days 수익률. 데이터가 n_days 미만이면 nan 반환."""
    if len(equity) < n_days:
        return float("nan")
    start_val = equity.iloc[-n_days]
    end_val = equity.iloc[-1]
    if start_val == 0:
        return float("nan")
    return float((end_val - start_val) / start_val)
