from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from quant_krx.config.profiles import EvaluationRules, get_profile
from quant_krx.quant.base import BacktestMetrics, BacktestResult


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WATCH = "watch"
    NO_SIGNAL = "no_signal"


@dataclass
class Signal:
    id: str
    run_id: str
    symbol: str
    signal_date: date
    signal_type: SignalType
    strategy_name: str
    strategy_display_name: str
    score: float                          # 0.0~1.0, 높을수록 강한 신호
    position_recommendation: str          # 사람이 읽을 수 있는 권고 문구
    evidence_metrics: BacktestMetrics
    risk_flags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "symbol": self.symbol,
            "signal_date": self.signal_date.isoformat(),
            "signal_type": self.signal_type.value,
            "strategy_name": self.strategy_name,
            "strategy_display_name": self.strategy_display_name,
            "score": self.score,
            "position_recommendation": self.position_recommendation,
            "risk_flags": self.risk_flags,
            "metrics": {
                "total_return": self.evidence_metrics.total_return,
                "benchmark_return": self.evidence_metrics.benchmark_return,
                "excess_return": self.evidence_metrics.excess_return,
                "mdd": self.evidence_metrics.mdd,
                "sharpe": self.evidence_metrics.sharpe,
                "sortino": self.evidence_metrics.sortino,
                "trade_count": self.evidence_metrics.trade_count,
                "fees_paid": self.evidence_metrics.fees_paid,
                "recent_6m_return": self.evidence_metrics.recent_6m_return,
                "recent_12m_return": self.evidence_metrics.recent_12m_return,
                "win_rate": self.evidence_metrics.win_rate,
                "benchmark_note": self.evidence_metrics.benchmark_note,
            },
        }


class SignalClassifier:
    """BacktestResult → Signal 결정론적 분류기."""

    def __init__(self, profile_name: str = "balanced"):
        self.rules: EvaluationRules = get_profile(profile_name)

    def classify(self, result: BacktestResult, signal_date: date | None = None) -> Signal:
        m = result.metrics
        risk_flags: list[str] = []
        score = 0.5  # 기본 중립 점수

        if signal_date is None:
            signal_date = result.end

        # --- 리스크 플래그 ---
        if m.mdd > self.rules.mdd_threshold:
            risk_flags.append(f"HIGH_MDD:{m.mdd:.1%}")

        if not math.isnan(m.sharpe) and m.sharpe < self.rules.sharpe_min:
            risk_flags.append(f"LOW_SHARPE:{m.sharpe:.2f}")

        if not math.isnan(m.recent_6m_return) and m.recent_6m_return < self.rules.recent_return_min:
            risk_flags.append(f"WEAK_RECENT_6M:{m.recent_6m_return:.1%}")

        if m.trade_count == 0:
            risk_flags.append("NO_TRADES")

        # --- 점수 계산 (0~1) ---
        # 초과 수익률 기여
        if not math.isnan(m.excess_return):
            score += min(0.2, max(-0.2, m.excess_return * 2))

        # Sharpe 기여
        if not math.isnan(m.sharpe):
            score += min(0.15, max(-0.15, (m.sharpe - 1.0) * 0.1))

        # MDD 페널티
        if m.mdd > self.rules.mdd_threshold:
            score -= 0.1

        # 최근 6개월 수익률 기여
        if not math.isnan(m.recent_6m_return):
            score += min(0.1, max(-0.1, m.recent_6m_return))

        score = max(0.0, min(1.0, score))

        # --- 신호 유형 결정 ---
        if len(risk_flags) >= 2:
            signal_type = SignalType.WATCH
        elif score >= 0.65 and not any("HIGH_MDD" in f or "NO_TRADES" in f for f in risk_flags):
            signal_type = SignalType.BUY
        elif score <= 0.35:
            signal_type = SignalType.SELL
        elif risk_flags:
            signal_type = SignalType.WATCH
        else:
            signal_type = SignalType.HOLD

        # --- 권고 문구 ---
        recommendation = self._make_recommendation(signal_type, m, risk_flags)

        signal_id = str(uuid.uuid4())
        return Signal(
            id=signal_id,
            run_id=result.run_id,
            symbol=result.symbol,
            signal_date=signal_date,
            signal_type=signal_type,
            strategy_name=result.strategy_name,
            strategy_display_name=result.strategy_display_name,
            score=round(score, 4),
            position_recommendation=recommendation,
            evidence_metrics=m,
            risk_flags=risk_flags,
        )

    def classify_batch(
        self,
        results: list[BacktestResult],
        signal_date: date | None = None,
    ) -> list[Signal]:
        return [self.classify(r, signal_date) for r in results]

    def _make_recommendation(
        self, signal_type: SignalType, m: BacktestMetrics, risk_flags: list[str]
    ) -> str:
        base = {
            SignalType.BUY: "매수 고려",
            SignalType.SELL: "매도 고려",
            SignalType.HOLD: "현 포지션 유지",
            SignalType.WATCH: "관망 (모니터링 권장)",
            SignalType.NO_SIGNAL: "신호 없음",
        }[signal_type]

        parts = [base]
        if not math.isnan(m.total_return):
            parts.append(f"누적수익률 {m.total_return:.1%}")
        if not math.isnan(m.sharpe):
            parts.append(f"Sharpe {m.sharpe:.2f}")
        if risk_flags:
            parts.append(f"주의: {', '.join(risk_flags)}")
        return " | ".join(parts)
