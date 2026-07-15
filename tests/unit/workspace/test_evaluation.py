from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from quant_krx.factors import FactorInput, compute_factor, get_factor
from quant_krx.formula.definition import BinaryOp, ConstantOperand, Formula
from quant_krx.formula.definition import FactorOperand as FormulaFactorOperand
from quant_krx.formula.definition import FormulaOperand as FormulaFormulaOperand
from quant_krx.rule.definition import Composition, FactorOperand, Predicate, Rule
from quant_krx.rule.definition import ConstantOperand as RuleConstantOperand
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.errors import EvaluationError, MissingDataError
from quant_krx.workspace.evaluation import (
    EvaluationContext,
    check_data_contract,
    evaluate_formula,
    evaluate_rule,
    strategy_required_data,
)

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sample_ohlcv.csv"


@pytest.fixture(scope="module")
def ohlcv() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE_PATH, dtype={"symbol": str}, parse_dates=["date"])
    df = df[df["symbol"] == "005930"].sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def _ctx(ohlcv: pd.DataFrame, store: dict | None = None) -> EvaluationContext:
    resolver = (store or {}).get
    return EvaluationContext(
        data=FactorInput(ohlcv=ohlcv), index=ohlcv.index, resolve_formula=resolver
    )


@pytest.fixture
def ctx(ohlcv) -> EvaluationContext:
    return _ctx(ohlcv)


def _rule_resolver(store: dict):
    return lambda key: store.get(key)


def _sma_formula(formula_id: str, window: int = 5) -> Formula:
    return Formula(
        id=formula_id, name=formula_id, version="1",
        expression=FormulaFactorOperand("sma", "sma", {"window": window}),
    )


def test_evaluate_formula_factor_operand_matches_compute_factor(ohlcv, ctx) -> None:
    formula = _sma_formula("m1", window=5)
    result = evaluate_formula(formula, ctx)
    expected = compute_factor(get_factor("sma", window=5), ohlcv)["sma"].reindex(ohlcv.index)
    assert_series_equal(result, expected, check_names=False)


def test_evaluate_formula_binary_arith(ohlcv, ctx) -> None:
    formula = Formula(
        id="m1", name="m1", version="1",
        expression=BinaryOp(
            op="*",
            left=FormulaFactorOperand("sma", "sma", {"window": 5}),
            right=ConstantOperand(2.0),
        ),
    )
    result = evaluate_formula(formula, ctx)
    base = compute_factor(get_factor("sma", window=5), ohlcv)["sma"].reindex(ohlcv.index)
    assert_series_equal(result, base * 2.0, check_names=False)


def test_evaluate_formula_multi_level_dag(ohlcv) -> None:
    base = _sma_formula("base", window=5)
    top = Formula(
        id="top", name="top", version="1",
        expression=BinaryOp(op="+", left=FormulaFormulaOperand("base"), right=ConstantOperand(1.0)),
    )
    ctx = _ctx(ohlcv, store={"base": base, "top": top})
    result = evaluate_formula(top, ctx)
    base_series = compute_factor(get_factor("sma", window=5), ohlcv)["sma"].reindex(ohlcv.index)
    assert_series_equal(result, base_series + 1.0, check_names=False)


def test_evaluate_formula_self_reference_raises(ohlcv) -> None:
    formula = Formula(
        id="self_ref", name="s", version="1", expression=FormulaFormulaOperand("self_ref")
    )
    ctx = _ctx(ohlcv, store={"self_ref": formula})
    with pytest.raises(EvaluationError):
        evaluate_formula(formula, ctx)


def test_evaluate_rule_comparison(ohlcv, ctx) -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(FactorOperand("sma", "sma", {"window": 5}), ">", RuleConstantOperand(0)),
    )
    result = evaluate_rule(rule, ctx)
    assert result.dtype == bool


def test_evaluate_rule_and_or_not(ohlcv, ctx) -> None:
    p1 = Predicate(FactorOperand("sma", "sma", {"window": 5}), ">", RuleConstantOperand(0))
    p2 = Predicate(FactorOperand("rsi", "rsi", {"window": 14}), "<", RuleConstantOperand(1000))
    and_rule = Rule(
        id="r_and", name="and", version="1", root=Composition(op="AND", operands=(p1, p2))
    )
    or_rule = Rule(
        id="r_or", name="or", version="1", root=Composition(op="OR", operands=(p1, p2))
    )
    not_rule = Rule(
        id="r_not", name="not", version="1", root=Composition(op="NOT", operands=(p1,))
    )

    r_and = evaluate_rule(and_rule, ctx)
    r_or = evaluate_rule(or_rule, ctx)
    r_not = evaluate_rule(not_rule, ctx)
    r1 = evaluate_rule(Rule(id="_p1", name="_p1", version="1", root=p1), ctx)
    r2 = evaluate_rule(Rule(id="_p2", name="_p2", version="1", root=p2), ctx)

    assert (r_and == (r1 & r2)).all()
    assert (r_or == (r1 | r2)).all()
    assert (r_not == (~r1)).all()


def test_evaluate_rule_params_override_and_golden_cross(ohlcv, ctx) -> None:
    sma5 = FactorOperand("sma", "sma", {"window": 5})
    sma20 = FactorOperand("sma", "sma", {"window": 20})
    cross_rule = Rule(
        id="golden", name="golden", version="1", root=Predicate(sma5, "crosses_above", sma20)
    )

    result = evaluate_rule(cross_rule, ctx)
    assert result.dtype == bool

    # 캐시가 파라미터별로 구분됨을 직접 확인
    from quant_krx.workspace.evaluation import _eval_factor_operand

    v5 = _eval_factor_operand("sma", "sma", {"window": 5}, ctx)
    v20 = _eval_factor_operand("sma", "sma", {"window": 20}, ctx)
    assert not v5.equals(v20)

    # 실제 골든크로스 발생 여부를 pandas로 독립 재도출해 대조(하드코딩 금지)
    expected = (v5 > v20) & (v5.shift(1) <= v20.shift(1))
    expected = expected & v5.notna() & v20.notna() & v5.shift(1).notna() & v20.shift(1).notna()
    assert (result == expected.astype(bool)).all()
    assert result.any()  # 픽스처 구간에서 실제 골든크로스가 발생함을 확인(AC-03)


def test_factor_cache_hit_avoids_recompute(ohlcv, ctx) -> None:
    import quant_krx.workspace.evaluation as ev_module

    calls = {"n": 0}
    original = ev_module.compute_factor

    def spy(factor, data):
        calls["n"] += 1
        return original(factor, data)

    ev_module.compute_factor = spy
    try:
        formula = _sma_formula("m1", window=5)
        evaluate_formula(formula, ctx)
        evaluate_formula(formula, ctx)
    finally:
        ev_module.compute_factor = original
    assert calls["n"] == 1


def test_deterministic_two_evaluations_equal(ohlcv) -> None:
    formula = _sma_formula("m1", window=5)
    ctx1 = _ctx(ohlcv)
    ctx2 = _ctx(ohlcv)
    assert_series_equal(evaluate_formula(formula, ctx1), evaluate_formula(formula, ctx2))


def test_strategy_required_data_ohlcv_only(ohlcv) -> None:
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FactorOperand("sma", "sma"), ">", RuleConstantOperand(0)),
    )
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    resolve_rule = _rule_resolver({"entry_rule": rule})
    required = strategy_required_data(defn, resolve_rule, lambda _: None)
    assert required == frozenset({"ohlcv"})


def test_check_data_contract_missing_valuation_raises(ohlcv) -> None:
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FactorOperand("per", "per"), ">", RuleConstantOperand(0)),
    )
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("per"),), universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    resolve_rule = _rule_resolver({"entry_rule": rule})
    ctx = _ctx(ohlcv)
    with pytest.raises(MissingDataError) as exc_info:
        check_data_contract(defn, ctx, resolve_rule)
    assert exc_info.value.kind == "valuation"
    assert "per" in exc_info.value.required_by


def test_check_data_contract_ohlcv_only_passes(ohlcv) -> None:
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FactorOperand("sma", "sma"), ">", RuleConstantOperand(0)),
    )
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    resolve_rule = _rule_resolver({"entry_rule": rule})
    ctx = _ctx(ohlcv)
    check_data_contract(defn, ctx, resolve_rule)  # 예외 없음


def test_factor_cache_isolated_across_contexts(ohlcv) -> None:
    # NFR-05: 캐시 수명은 단일 (전략,종목) EvaluationContext 한정 — 컨텍스트 간 dict 공유 금지.
    formula = _sma_formula("m1", window=5)
    ctx1 = _ctx(ohlcv)
    ctx2 = _ctx(ohlcv)

    evaluate_formula(formula, ctx1)

    assert ctx1._factor_cache is not ctx2._factor_cache
    assert ("sma", '{"window":5}') in ctx1._factor_cache
    assert ctx2._factor_cache == {}  # 별개 컨텍스트는 아무 것도 물려받지 않는다
