from __future__ import annotations

from datetime import date

import pytest

from quant_krx.workspace.dynamic_universe import (
    DynamicUniversePlan,
    anchor_dates,
    build_plan,
)
from quant_krx.workspace.errors import EvaluationError

START = date(2024, 1, 15)
END = date(2024, 6, 30)


# --- anchor_dates ---


def test_anchor_dates_monthly_includes_start():
    """시작일이 월 중간이어도 첫 앵커로 포함돼야 첫 구간이 비지 않는다."""
    anchors = anchor_dates(START, END, "monthly")
    assert anchors[0] == START
    assert date(2024, 2, 1) in anchors
    assert date(2024, 6, 1) in anchors


def test_anchor_dates_quarterly_is_sparser_than_monthly():
    monthly = anchor_dates(date(2024, 1, 1), date(2024, 12, 31), "monthly")
    quarterly = anchor_dates(date(2024, 1, 1), date(2024, 12, 31), "quarterly")
    weekly = anchor_dates(date(2024, 1, 1), date(2024, 12, 31), "weekly")
    assert len(weekly) > len(monthly) > len(quarterly)


def test_anchor_dates_does_not_duplicate_start_when_aligned():
    anchors = anchor_dates(date(2024, 1, 1), date(2024, 3, 31), "monthly")
    assert anchors.count(date(2024, 1, 1)) == 1


def test_anchor_dates_unknown_frequency_rejected():
    with pytest.raises(EvaluationError, match="미지의 rebalance"):
        anchor_dates(START, END, "daily")


# --- backward 매칭 ---


def _plan() -> DynamicUniversePlan:
    return DynamicUniversePlan(
        screening_id="cond",
        by_anchor={
            date(2024, 1, 1): ("005930", "000660"),
            date(2024, 2, 1): ("006400",),
            date(2024, 3, 1): (),
        },
    )


def test_eligible_at_uses_most_recent_anchor():
    """앵커(달력)와 실제 리밸런싱일(거래일)이 어긋나도 직전 앵커 결과를 쓴다."""
    plan = _plan()
    assert set(plan.eligible_at("cond", date(2024, 1, 15))) == {"005930", "000660"}
    assert set(plan.eligible_at("cond", date(2024, 2, 5))) == {"006400"}


def test_eligible_at_on_exact_anchor():
    assert set(_plan().eligible_at("cond", date(2024, 2, 1))) == {"006400"}


def test_eligible_at_before_first_anchor_is_empty():
    """첫 앵커 이전 구간은 유니버스가 정해지지 않았으므로 빈 목록이다."""
    assert _plan().eligible_at("cond", date(2023, 12, 31)) == []


def test_eligible_at_empty_anchor_stays_empty():
    """통과 종목이 0인 시점은 그대로 0이어야 한다(직전 앵커로 되돌아가면 안 됨)."""
    assert _plan().eligible_at("cond", date(2024, 3, 10)) == []


def test_eligible_at_rejects_other_screening_id():
    with pytest.raises(EvaluationError, match="계획에 없는 스크리닝"):
        _plan().eligible_at("other", date(2024, 2, 1))


def test_symbols_is_union_of_all_anchors():
    assert _plan().symbols == ["000660", "005930", "006400"]


# --- build_plan ---


def test_build_plan_calls_resolver_per_anchor():
    calls: list[date] = []

    def _resolve(condition_id: str, as_of: date) -> list[str]:
        calls.append(as_of)
        return ["005930"]

    plan = build_plan(
        "cond", start=date(2024, 1, 1), end=date(2024, 3, 31),
        rebalance="monthly", resolve=_resolve,
    )

    assert calls == [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)]
    assert plan.symbols == ["005930"]


def test_build_plan_isolates_failing_anchor():
    """한 시점 스크리닝이 실패해도 나머지 구간은 정상 실행돼야 한다."""

    def _resolve(condition_id: str, as_of: date) -> list[str]:
        if as_of == date(2024, 2, 1):
            raise RuntimeError("일시적 조회 실패")
        return ["005930"]

    plan = build_plan(
        "cond", start=date(2024, 1, 1), end=date(2024, 3, 31),
        rebalance="monthly", resolve=_resolve,
    )

    assert plan.by_anchor[date(2024, 2, 1)] == ()
    assert plan.symbols == ["005930"]
    # 실패한 시점은 빈 유니버스 = 그 구간 현금 보유
    assert plan.eligible_at("cond", date(2024, 2, 10)) == []


def test_build_plan_all_failures_yield_empty_universe():
    def _resolve(condition_id: str, as_of: date) -> list[str]:
        raise RuntimeError("전면 실패")

    plan = build_plan(
        "cond", start=date(2024, 1, 1), end=date(2024, 3, 31),
        rebalance="monthly", resolve=_resolve,
    )
    assert plan.symbols == []


def test_build_plan_reports_progress():
    seen: list[tuple[int, int]] = []
    build_plan(
        "cond", start=date(2024, 1, 1), end=date(2024, 3, 31),
        rebalance="monthly", resolve=lambda _c, _d: [],
        on_progress=lambda done, total, anchor: seen.append((done, total)),
    )
    assert seen == [(1, 3), (2, 3), (3, 3)]
