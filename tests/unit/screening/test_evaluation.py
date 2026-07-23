from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_series_equal

import quant_krx.screening.evaluation as scr_eval
from quant_krx.screening.definition import (
    Composition,
    ConstantOperand,
    FactorOperand,
    FormulaOperand,
    Predicate,
    RankPredicate,
    WindowPredicate,
)
from quant_krx.screening.errors import ScreeningError
from quant_krx.screening.evaluation import (
    ScreeningEvaluationContext,
    _apply_window,
    _eval_screening_node,
    default_factor_lookback_resolver,
    estimate_required_lookback,
    extract_rank_predicates,
)
from quant_krx.workspace import numeric as numeric_mod

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sample_ohlcv.csv"


@pytest.fixture(scope="module")
def ohlcv() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE_PATH, dtype={"symbol": str}, parse_dates=["date"])
    df = df[df["symbol"] == "005930"].sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def _ctx(ohlcv: pd.DataFrame) -> ScreeningEvaluationContext:
    return ScreeningEvaluationContext(ohlcv=ohlcv, index=ohlcv.index)


# --- leaf가 workspace.numeric.compare/crosses를 실제로 호출하는지 -----------------


def test_predicate_comparison_delegates_to_numeric_compare(ohlcv, monkeypatch) -> None:
    calls: list[str] = []
    real_compare = numeric_mod.compare

    def spy_compare(op, left, right):
        calls.append(op)
        return real_compare(op, left, right)

    monkeypatch.setattr(scr_eval, "compare", spy_compare)

    node = Predicate(
        left=FactorOperand(factor_id="sma", column="sma", params={"window": 5}),
        operator=">",
        right=ConstantOperand(value=0),
    )
    result = _eval_screening_node(node, _ctx(ohlcv))

    assert calls == [">"]
    assert result.dtype == bool


def test_predicate_cross_delegates_to_numeric_crosses(ohlcv, monkeypatch) -> None:
    calls: list[str] = []
    real_crosses = numeric_mod.crosses

    def spy_crosses(direction, left, right):
        calls.append(direction)
        return real_crosses(direction, left, right)

    monkeypatch.setattr(scr_eval, "crosses", spy_crosses)

    node = Predicate(
        left=FactorOperand(factor_id="sma", column="sma", params={"window": 5}),
        operator="crosses_above",
        right=FactorOperand(factor_id="sma", column="sma", params={"window": 20}),
    )
    result = _eval_screening_node(node, _ctx(ohlcv))

    assert calls == ["crosses_above"]
    assert result.dtype == bool


def test_screening_evaluation_imports_numeric_helpers_directly() -> None:
    """compare/crosses/broadcast가 workspace.numeric의 바로 그 함수 객체인지 정적 확인."""
    assert scr_eval.compare is numeric_mod.compare
    assert scr_eval.crosses is numeric_mod.crosses
    assert scr_eval.broadcast is numeric_mod.broadcast


# --- WindowPredicate 경계값 -----------------------------------------------------


def _cross_ohlcv() -> pd.DataFrame:
    """골든크로스(sma3가 sma8 위로)가 정확히 마지막 봉 기준 3봉 전에 발생하도록 만든 합성 OHLCV.

    평탄 구간 뒤 단조 상승으로 크로스가 정확히 1회 발생한다. 크로스 위치를 프로그램으로 찾아
    그 지점이 끝에서 3봉 전(len-4)이 되도록 꼬리를 잘라 결정론적으로 고정한다.
    """
    prices = [100.0] * 15 + [100.0 + i for i in range(1, 21)]
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    df = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": 1.0},
        index=idx,
    )

    probe_ctx = ScreeningEvaluationContext(ohlcv=df, index=idx)
    inner = _eval_screening_node(_golden_cross_pred(), probe_ctx)
    cross_positions = [i for i, v in enumerate(inner.to_numpy()) if v]
    assert len(cross_positions) == 1, f"크로스는 정확히 1회여야 함: {cross_positions}"
    cross_pos = cross_positions[0]
    # 크로스가 끝에서 3봉 전(마지막 인덱스 = cross_pos + 3)이 되도록 꼬리를 자른다.
    return df.iloc[: cross_pos + 4]


def _golden_cross_pred() -> Predicate:
    return Predicate(
        left=FactorOperand(factor_id="sma", column="sma", params={"window": 3}),
        operator="crosses_above",
        right=FactorOperand(factor_id="sma", column="sma", params={"window": 8}),
    )


def test_window_predicate_boundaries() -> None:
    df = _cross_ohlcv()
    ctx = _ctx(df)
    inner_pred = _golden_cross_pred()
    inner = _eval_screening_node(inner_pred, ctx)
    # 크로스는 정확히 마지막 봉 기준 3봉 전.
    assert bool(inner.iloc[-4]) is True
    assert not inner.iloc[-3:].any()

    # n_bars=5, 현재봉 포함: 3봉 전 크로스가 창(과거 5봉) 안에 들어와 현재봉 True.
    w5 = WindowPredicate(inner=inner_pred, n_bars=5, include_current_bar=True)
    assert bool(_eval_screening_node(w5, ctx).iloc[-1]) is True

    # n_bars=2, 현재봉 포함: 3봉 전 크로스가 창(과거 2봉) 밖이라 현재봉 False.
    w2 = WindowPredicate(inner=inner_pred, n_bars=2, include_current_bar=True)
    assert bool(_eval_screening_node(w2, ctx).iloc[-1]) is False

    # n_bars=0, 현재봉 포함: 원본과 완전히 동일.
    w0_incl = WindowPredicate(inner=inner_pred, n_bars=0, include_current_bar=True)
    assert_series_equal(_eval_screening_node(w0_incl, ctx), inner, check_names=False)

    # n_bars=0, 현재봉 제외: 과거도 현재도 안 보므로 전부 False.
    w0_excl = WindowPredicate(inner=inner_pred, n_bars=0, include_current_bar=False)
    assert not _eval_screening_node(w0_excl, ctx).any()


def test_apply_window_exclude_current_bar_shifts() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    series = pd.Series([True, False, False, False, False], index=idx)
    # 현재봉 제외 과거 3봉: 인덱스 0의 True가 인덱스 1..3에서 창 안에 잡히고, 4에서는 벗어난다.
    result = _apply_window(series, n_bars=3, include_current_bar=False)
    assert list(result) == [False, True, True, True, False]


# --- extract_rank_predicates ----------------------------------------------------


def test_extract_rank_predicates_collects_from_nested_tree() -> None:
    rank1 = RankPredicate(factor_id="momentum", column="value", rank_metric="desc", top_n=10)
    rank2 = RankPredicate(factor_id="rsi", column="value", rank_metric="asc", top_n=5)
    rank3 = RankPredicate(factor_id="volume", column="value", rank_metric="desc", top_n=20)
    plain = Predicate(
        left=FactorOperand(factor_id="sma", column="sma", params={"window": 5}),
        operator=">",
        right=ConstantOperand(value=0),
    )
    tree = Composition(
        op="AND",
        operands=(
            Composition(op="OR", operands=(rank1, plain)),
            WindowPredicate(
                inner=Composition(op="OR", operands=(rank2, plain)),
                n_bars=3,
                include_current_bar=True,
            ),
            rank3,
        ),
    )
    collected = extract_rank_predicates(tree)
    assert len(collected) == 3
    assert sorted(r.factor_id for r in collected) == ["momentum", "rsi", "volume"]


def test_extract_rank_predicates_none_present() -> None:
    node = Predicate(
        left=FactorOperand(factor_id="sma", column="sma", params={"window": 5}),
        operator=">",
        right=ConstantOperand(value=0),
    )
    assert extract_rank_predicates(node) == []


# --- RankPredicate는 트리 순회 평가에서 거부 -----------------------------------


def test_rank_predicate_rejected_when_membership_absent(ohlcv) -> None:
    """rank_membership 미제공(None)이면 기존처럼 거부해 하위 호환을 유지한다."""
    node = RankPredicate(factor_id="momentum", column="value", rank_metric="desc", top_n=10)
    with pytest.raises(ScreeningError, match="RankPredicate"):
        _eval_screening_node(node, _ctx(ohlcv))


def test_rank_predicate_resolved_from_membership(ohlcv) -> None:
    """rank_membership 제공 시 현재 종목 소속 여부로 상수 bool Series를 반환한다."""
    node = RankPredicate(factor_id="momentum", column="close", rank_metric="desc", top_n=10)

    passing_ctx = ScreeningEvaluationContext(
        ohlcv=ohlcv, index=ohlcv.index, rank_membership={node: {"005930"}}, current_symbol="005930"
    )
    passing = _eval_screening_node(node, passing_ctx)
    assert passing.dtype == bool
    assert passing.all()
    assert len(passing) == len(ohlcv.index)

    failing_ctx = ScreeningEvaluationContext(
        ohlcv=ohlcv, index=ohlcv.index, rank_membership={node: {"000660"}}, current_symbol="005930"
    )
    failing = _eval_screening_node(node, failing_ctx)
    assert not failing.any()


def test_rank_predicate_missing_from_membership_raises(ohlcv) -> None:
    """rank_membership에 해당 predicate 사전 계산이 없으면 명확히 거부한다."""
    node = RankPredicate(factor_id="momentum", column="close", rank_metric="desc", top_n=10)
    other = RankPredicate(factor_id="rsi", column="volume", rank_metric="asc", top_n=5)
    ctx = ScreeningEvaluationContext(
        ohlcv=ohlcv, index=ohlcv.index, rank_membership={other: set()}, current_symbol="005930"
    )
    with pytest.raises(ScreeningError, match="rank_membership"):
        _eval_screening_node(node, ctx)


def test_formula_operand_rejected_in_leaf_evaluation(ohlcv) -> None:
    node = Predicate(
        left=FormulaOperand(formula_id="custom"),
        operator=">",
        right=ConstantOperand(value=0),
    )
    with pytest.raises(ScreeningError, match="FormulaOperand"):
        _eval_screening_node(node, _ctx(ohlcv))


# --- estimate_required_lookback -------------------------------------------------


def test_default_factor_lookback_resolver() -> None:
    assert default_factor_lookback_resolver("sma", {"window": 20}) == 25
    assert default_factor_lookback_resolver("macd", {"slow": 26, "signal": 9}) == 31
    assert default_factor_lookback_resolver("price", {}) == 60


def test_estimate_required_lookback_sums_window_over_inner() -> None:
    inner = Predicate(
        left=FactorOperand(factor_id="sma", column="sma", params={"window": 20}),
        operator=">",
        right=ConstantOperand(value=0),
    )
    window = WindowPredicate(inner=inner, n_bars=5, include_current_bar=True)
    other = Predicate(
        left=FactorOperand(factor_id="rolling_high", column="value", params={"window": 100}),
        operator=">",
        right=ConstantOperand(value=0),
    )
    tree = Composition(op="AND", operands=(window, other))
    # window 분기: n_bars(5) + inner(window 20 + 5 = 25) = 30. other 분기: 100 + 5 = 105.
    # 분기 사이는 최댓값 → 105.
    result = estimate_required_lookback(
        tree, factor_lookback_resolver=default_factor_lookback_resolver
    )
    assert result == 105
