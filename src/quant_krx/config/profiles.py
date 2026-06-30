from dataclasses import dataclass


@dataclass
class EvaluationRules:
    name: str
    mdd_threshold: float  # MDD > this → risk_flag
    sharpe_min: float  # Sharpe < this → score penalty
    recent_return_min: float  # 최근 수익률 < this → hold/watch 고려
    recent_months: int


PROFILES = {
    "balanced": EvaluationRules(
        name="balanced",
        mdd_threshold=0.30,
        sharpe_min=0.5,
        recent_return_min=-0.10,
        recent_months=6,
    ),
    "aggressive": EvaluationRules(
        name="aggressive",
        mdd_threshold=0.50,
        sharpe_min=0.3,
        recent_return_min=-0.20,
        recent_months=3,
    ),
    "conservative": EvaluationRules(
        name="conservative",
        mdd_threshold=0.15,
        sharpe_min=0.8,
        recent_return_min=-0.05,
        recent_months=12,
    ),
    "research": EvaluationRules(
        name="research",
        mdd_threshold=1.00,  # 제한 없음
        sharpe_min=0.0,
        recent_return_min=-1.00,
        recent_months=6,
    ),
}


def get_profile(name: str) -> EvaluationRules:
    if name not in PROFILES:
        raise ValueError(f"Unknown profile: {name}. Available: {list(PROFILES)}")
    return PROFILES[name]
