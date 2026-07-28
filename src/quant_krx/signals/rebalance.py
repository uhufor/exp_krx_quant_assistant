"""리밸런싱 지시 계산(R05) — 포트폴리오 신호 생성의 입력.

`jobs/`가 아니라 `signals/`에 두는 이유: 이 계산은 순수 함수이고 `SignalClassifier`가
직접 소비하므로, `signals` → `jobs` 역방향 import를 만들지 않기 위함이다.

포트폴리오 백테스트가 만든 목표 비중 이력(`BacktestReport.weights`)만으로 "오늘 무엇을
사고 팔아야 하는가"를 도출하는 순수 계산이다. 새로 계산하는 값은 없고 마지막 두 배분의
차집합만 취한다.

**현재 보유의 정의(사용자 확정 D3)**: 시스템은 실제 계좌를 모르므로 *직전 리밸런싱 시점의
목표 비중*을 현재 보유로 간주한다 — 사용자가 전략을 그대로 따랐다는 가정이며, 리포트는 이
가정을 숨기지 않고 명시한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class PositionChange:
    """한 종목의 목표 대비 변화. weight는 비중(0.0~1.0)."""

    symbol: str
    target_weight: float = 0.0
    current_weight: float = 0.0

    @property
    def delta(self) -> float:
        return self.target_weight - self.current_weight


@dataclass(frozen=True)
class RebalancePlan:
    """오늘 기준 리밸런싱 지시."""

    rebalance_date: date | None          # 목표 비중이 정해진 마지막 리밸런싱일
    previous_date: date | None           # 그 직전 리밸런싱일(최초 진입이면 None)
    is_rebalance_day: bool               # 오늘이 그 리밸런싱일인가
    entries: tuple[PositionChange, ...] = ()   # 신규 편입
    exits: tuple[PositionChange, ...] = ()     # 전량 제외
    holds: tuple[PositionChange, ...] = ()     # 유지(비중 변화량 포함)
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_changes(self) -> bool:
        """실제 매매가 필요한가 — 편입·제외가 있거나 유지 종목의 비중이 달라졌는가."""
        return bool(self.entries or self.exits) or any(
            abs(h.delta) > _WEIGHT_EPSILON for h in self.holds
        )

    @property
    def target_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(c.symbol for c in self.entries + self.holds))

    @property
    def targets(self) -> tuple[PositionChange, ...]:
        """지금 보유하고 있어야 할 종목과 목표 비중(종목코드 순).

        리밸런싱일이 아닌 날 "현재 이래야 한다"를 보여주기 위한 것으로, 매매 지시(entries/
        exits)와는 쓰임이 다르다 — 지시는 리밸런싱 당일에만 유효하다.
        """
        return tuple(sorted(self.entries + self.holds, key=lambda c: c.symbol))

    def summary(self) -> str:
        """신호 문구용 한 줄 요약."""
        if self.rebalance_date is None:
            return "리밸런싱 이력 없음"
        if not self.has_changes:
            return f"변경 없음 · 보유 {len(self.holds)}종목"
        return (
            f"신규 편입 {len(self.entries)} · 제외 {len(self.exits)} · 유지 {len(self.holds)}"
        )


# 부동소수 비교 여유값 — 균등 분배 비중(1/3 등)의 표현 오차를 변화로 오인하지 않는다.
_WEIGHT_EPSILON = 1e-9


def _parse(key: str) -> date:
    return date.fromisoformat(key)


def diff_weights(
    weights: dict[str, dict[str, float]], as_of: date
) -> RebalancePlan:
    """목표 비중 이력에서 오늘 기준 리밸런싱 지시를 만든다.

    `weights`는 `{"YYYY-MM-DD": {symbol: 비중}}`이며 0 비중은 이미 생략되어 있으므로
    키 집합이 곧 보유 종목이다. as_of 이후의 리밸런싱은 아직 오지 않은 미래이므로 제외한다
    (백테스트를 as_of까지만 돌리면 발생하지 않지만, 방어적으로 잘라낸다).
    """
    dates = sorted(d for d in weights if _parse(d) <= as_of)
    if not dates:
        return RebalancePlan(
            rebalance_date=None, previous_date=None, is_rebalance_day=False,
            notes=("리밸런싱 이력이 없습니다(기간이 짧거나 대상 종목이 없습니다)",),
        )

    last_key = dates[-1]
    prev_key = dates[-2] if len(dates) >= 2 else None
    target = weights[last_key]
    current = weights[prev_key] if prev_key is not None else {}

    entries = tuple(
        PositionChange(symbol=s, target_weight=target[s], current_weight=0.0)
        for s in sorted(set(target) - set(current))
    )
    exits = tuple(
        PositionChange(symbol=s, target_weight=0.0, current_weight=current[s])
        for s in sorted(set(current) - set(target))
    )
    holds = tuple(
        PositionChange(symbol=s, target_weight=target[s], current_weight=current[s])
        for s in sorted(set(target) & set(current))
    )

    return RebalancePlan(
        rebalance_date=_parse(last_key),
        previous_date=_parse(prev_key) if prev_key is not None else None,
        is_rebalance_day=_parse(last_key) == as_of,
        entries=entries,
        exits=exits,
        holds=holds,
    )
