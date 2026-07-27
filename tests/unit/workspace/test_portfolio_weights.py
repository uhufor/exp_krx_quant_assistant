from __future__ import annotations

import pandas as pd
import pytest

from quant_krx.strategy.definition import PortfolioPolicy, RankingSpec
from quant_krx.workspace.errors import EvaluationError
from quant_krx.workspace.portfolio import (
    build_target_weights,
    holding_intent,
    rebalance_dates,
)

SYMBOLS = ["000660", "005930", "006400"]


def _frame(index: pd.DatetimeIndex, rows: dict[str, list[bool]]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=index)


def _index(periods: int, start: str = "2024-01-01", freq: str = "D") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=periods, freq=freq)


# --- holding_intent ---


def test_holding_intent_persists_between_signals():
    """진입 신호 이후 청산 전까지 보유 상태가 유지되어야 한다."""
    index = _index(5)
    entries = _frame(index, {"A": [False, True, False, False, False]})
    exits = _frame(index, {"A": [False, False, False, True, False]})

    intent = holding_intent(entries, exits)
    assert list(intent["A"]) == [False, True, True, False, False]


def test_holding_intent_starts_flat_without_entry():
    index = _index(3)
    entries = _frame(index, {"A": [False, False, False]})
    exits = _frame(index, {"A": [False, False, False]})
    assert list(holding_intent(entries, exits)["A"]) == [False, False, False]


def test_holding_intent_exit_wins_on_same_day():
    """진입·청산이 같은 날 동시 발생하면 보유하지 않는다(보수적 처리)."""
    index = _index(3)
    entries = _frame(index, {"A": [True, False, False]})
    exits = _frame(index, {"A": [True, False, False]})
    assert list(holding_intent(entries, exits)["A"]) == [False, False, False]


def test_holding_intent_reentry_after_exit():
    index = _index(5)
    entries = _frame(index, {"A": [True, False, False, True, False]})
    exits = _frame(index, {"A": [False, True, False, False, False]})
    assert list(holding_intent(entries, exits)["A"]) == [True, False, False, True, True]


# --- rebalance_dates ---


def test_rebalance_dates_monthly_picks_first_trading_day():
    """달력 1일이 아니라 실제 데이터에 존재하는 첫 거래일이 선택되어야 한다."""
    index = pd.DatetimeIndex(["2024-01-03", "2024-01-15", "2024-02-05", "2024-02-20"])
    assert list(rebalance_dates(index, "monthly")) == [
        pd.Timestamp("2024-01-03"),
        pd.Timestamp("2024-02-05"),
    ]


def test_rebalance_dates_always_includes_first_bar():
    """첫날이 빠지면 첫 구간 내내 포지션이 비게 되므로 반드시 포함되어야 한다."""
    index = pd.DatetimeIndex(["2024-01-20", "2024-01-25", "2024-02-01"])
    assert rebalance_dates(index, "monthly")[0] == pd.Timestamp("2024-01-20")


def test_rebalance_dates_quarterly_and_weekly_differ_in_count():
    index = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    weekly = len(rebalance_dates(index, "weekly"))
    monthly = len(rebalance_dates(index, "monthly"))
    quarterly = len(rebalance_dates(index, "quarterly"))
    assert weekly > monthly > quarterly
    assert monthly == 12
    assert quarterly == 4


def test_rebalance_dates_empty_index():
    assert len(rebalance_dates(pd.DatetimeIndex([]), "monthly")) == 0


def test_rebalance_dates_unknown_frequency_rejected():
    with pytest.raises(EvaluationError, match="미지의 rebalance"):
        rebalance_dates(_index(3), "daily")


# --- build_target_weights ---


def _policy(**kwargs) -> PortfolioPolicy:
    return PortfolioPolicy(**{"max_positions": 2, "rebalance": "monthly", **kwargs})


def test_weights_only_on_rebalance_dates():
    """리밸런싱일 외에는 NaN(주문 없음)이어야 거래가 그날에만 발생한다."""
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-10", "2024-02-01"])
    entries = _frame(index, {"A": [True, True, True]})
    exits = _frame(index, {"A": [False, False, False]})

    weights = build_target_weights(entries, exits, _policy())
    assert weights.loc[pd.Timestamp("2024-01-10")].isna().all()
    assert not weights.loc[pd.Timestamp("2024-01-02")].isna().any()
    assert not weights.loc[pd.Timestamp("2024-02-01")].isna().any()


def test_weights_are_equal_among_selected():
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {"A": [True], "B": [True]})
    exits = _frame(index, {"A": [False], "B": [False]})

    weights = build_target_weights(entries, exits, _policy(max_positions=2))
    assert weights.loc[index[0], "A"] == pytest.approx(0.5)
    assert weights.loc[index[0], "B"] == pytest.approx(0.5)


def test_weights_use_selected_count_not_max_positions():
    """후보가 N보다 적으면 1/N이 아니라 1/k로 배분해 자본을 놀리지 않는다."""
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {"A": [True], "B": [False]})
    exits = _frame(index, {"A": [False], "B": [False]})

    weights = build_target_weights(entries, exits, _policy(max_positions=4))
    assert weights.loc[index[0], "A"] == pytest.approx(1.0)
    assert weights.loc[index[0], "B"] == pytest.approx(0.0)


def test_weights_cap_at_max_positions():
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {s: [True] for s in SYMBOLS})
    exits = _frame(index, {s: [False] for s in SYMBOLS})

    weights = build_target_weights(entries, exits, _policy(max_positions=2))
    row = weights.loc[index[0]]
    assert (row > 0).sum() == 2
    assert row.sum() == pytest.approx(1.0)


def test_weights_without_ranking_use_symbol_code_order():
    """ranking 미지정 시 종목코드 오름차순 — 임의 기준을 몰래 쓰지 않고 결정론만 보장."""
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {s: [True] for s in SYMBOLS})
    exits = _frame(index, {s: [False] for s in SYMBOLS})

    weights = build_target_weights(entries, exits, _policy(max_positions=2))
    selected = sorted(weights.loc[index[0]][weights.loc[index[0]] > 0].index)
    assert selected == ["000660", "005930"]


def test_weights_ranking_descending_picks_highest():
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {s: [True] for s in SYMBOLS})
    exits = _frame(index, {s: [False] for s in SYMBOLS})
    scores = pd.DataFrame({"000660": [1.0], "005930": [5.0], "006400": [9.0]}, index=index)
    policy = _policy(
        max_positions=2,
        ranking=RankingSpec(kind="factor", factor_id="sma", column="sma", descending=True),
    )

    weights = build_target_weights(entries, exits, policy, ranking_scores=scores)
    selected = set(weights.loc[index[0]][weights.loc[index[0]] > 0].index)
    assert selected == {"006400", "005930"}


def test_weights_ranking_ascending_picks_lowest():
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {s: [True] for s in SYMBOLS})
    exits = _frame(index, {s: [False] for s in SYMBOLS})
    scores = pd.DataFrame({"000660": [1.0], "005930": [5.0], "006400": [9.0]}, index=index)
    policy = _policy(
        max_positions=2,
        ranking=RankingSpec(kind="factor", factor_id="per", column="per", descending=False),
    )

    weights = build_target_weights(entries, exits, policy, ranking_scores=scores)
    selected = set(weights.loc[index[0]][weights.loc[index[0]] > 0].index)
    assert selected == {"000660", "005930"}


def test_weights_ranking_excludes_nan_scores():
    """점수가 NaN인 종목은 순위를 매길 수 없으므로 후보에서 제외한다."""
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {s: [True] for s in SYMBOLS})
    exits = _frame(index, {s: [False] for s in SYMBOLS})
    scores = pd.DataFrame(
        {"000660": [float("nan")], "005930": [5.0], "006400": [9.0]}, index=index
    )
    policy = _policy(
        max_positions=3,
        ranking=RankingSpec(kind="factor", factor_id="sma", column="sma"),
    )

    weights = build_target_weights(entries, exits, policy, ranking_scores=scores)
    row = weights.loc[index[0]]
    assert row["000660"] == pytest.approx(0.0)
    assert row["005930"] == pytest.approx(0.5)
    assert row["006400"] == pytest.approx(0.5)


def test_weights_ranking_ties_broken_by_symbol_code():
    """동점이어도 실행마다 결과가 흔들리면 안 된다(결정론 불변식)."""
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {s: [True] for s in SYMBOLS})
    exits = _frame(index, {s: [False] for s in SYMBOLS})
    scores = pd.DataFrame({s: [3.0] for s in SYMBOLS}, index=index)
    policy = _policy(
        max_positions=2, ranking=RankingSpec(kind="factor", factor_id="sma", column="sma")
    )

    first = build_target_weights(entries, exits, policy, ranking_scores=scores)
    second = build_target_weights(entries, exits, policy, ranking_scores=scores)
    pd.testing.assert_frame_equal(first, second)
    selected = sorted(first.loc[index[0]][first.loc[index[0]] > 0].index)
    assert selected == ["000660", "005930"]


def test_weights_exited_symbol_gets_explicit_zero():
    """청산된 종목은 NaN이 아니라 0이어야 실제로 매도된다(NaN은 기존 비중 유지)."""
    index = pd.DatetimeIndex(["2024-01-02", "2024-02-01"])
    entries = _frame(index, {"A": [True, False]})
    exits = _frame(index, {"A": [False, True]})

    weights = build_target_weights(entries, exits, _policy())
    assert weights.loc[pd.Timestamp("2024-01-02"), "A"] == pytest.approx(1.0)
    assert weights.loc[pd.Timestamp("2024-02-01"), "A"] == pytest.approx(0.0)


def test_weights_all_zero_when_no_candidates():
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {"A": [False], "B": [False]})
    exits = _frame(index, {"A": [False], "B": [False]})

    weights = build_target_weights(entries, exits, _policy())
    assert (weights.loc[index[0]] == 0.0).all()


def test_weights_exclude_untradable_symbols():
    """상장 전·데이터 결손 구간의 종목은 신호가 있어도 매수 후보가 되면 안 된다."""
    index = pd.DatetimeIndex(["2024-01-02"])
    entries = _frame(index, {"A": [True], "B": [True]})
    exits = _frame(index, {"A": [False], "B": [False]})
    tradable = _frame(index, {"A": [True], "B": [False]})

    weights = build_target_weights(entries, exits, _policy(), tradable=tradable)
    assert weights.loc[index[0], "A"] == pytest.approx(1.0)
    assert weights.loc[index[0], "B"] == pytest.approx(0.0)


def test_weights_never_exceed_full_allocation():
    """어떤 리밸런싱일에도 목표 비중 합이 100%를 넘지 않아야 한다(레버리지 방지)."""
    index = pd.date_range("2024-01-01", periods=120, freq="D")
    entries = _frame(index, {s: [True] * 120 for s in SYMBOLS})
    exits = _frame(index, {s: [False] * 120 for s in SYMBOLS})

    weights = build_target_weights(entries, exits, _policy(max_positions=2))
    sums = weights.dropna(how="all").sum(axis=1)
    assert (sums <= 1.0 + 1e-9).all()
