from __future__ import annotations

import pytest

from quant_krx._jsonnorm import DefinitionValidationError
from quant_krx.formula.definition import FactorOperand as FormulaFactorOperand
from quant_krx.formula.definition import Formula
from quant_krx.rule.definition import FactorOperand as RuleFactorOperand
from quant_krx.rule.definition import FormulaOperand as RuleFormulaOperand
from quant_krx.rule.definition import Predicate, Rule
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.strategy.validation import (
    is_runnable,
    validate_definition,
    validate_definition_strict,
)


def _resolver(store: dict):
    return lambda key: store.get(key)


def test_draft_definition_passes_and_not_runnable() -> None:
    defn = StrategyDefinition(
        id="my_strategy", name="내 전략", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}),), universe=Universe(), rule=None,
    )
    result = validate_definition(defn)
    assert result.ok
    assert not is_runnable(defn)


def test_non_snake_case_id_rejected() -> None:
    defn = StrategyDefinition(
        id="MyStrategy", name="x", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    result = validate_definition(defn)
    assert not result.ok


def test_unknown_factor_ref_rejected() -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("no_such_factor"),), universe=Universe(), rule=None,
    )
    result = validate_definition(defn)
    assert not result.ok
    assert any("no_such_factor" in e for e in result.errors)


def test_factor_ref_param_violation_rejected() -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma", {"window": -1}),), universe=Universe(), rule=None,
    )
    result = validate_definition(defn)
    assert not result.ok


def test_rule_reference_missing_rejected() -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(),
        rule=RuleBinding(entry=("missing_rule",)),
    )
    result = validate_definition(defn, resolve_rule=_resolver({}))
    assert not result.ok
    assert any("missing_rule" in e for e in result.errors)


def test_factor_refs_consistency_exact_match_passes() -> None:
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(RuleFactorOperand("sma", "sma"), ">", RuleFactorOperand("per", "per")),
    )
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"), FactorRef("per")),
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    result = validate_definition(defn, resolve_rule=_resolver({"entry_rule": rule}))
    assert result.ok
    assert is_runnable(defn)


def test_factor_refs_missing_declaration_rejected() -> None:
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(RuleFactorOperand("sma", "sma"), ">", RuleFactorOperand("per", "per")),
    )
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),),  # per 누락
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    result = validate_definition(defn, resolve_rule=_resolver({"entry_rule": rule}))
    assert not result.ok
    assert any("누락" in e for e in result.errors)


def test_factor_refs_extra_declaration_rejected() -> None:
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(RuleFactorOperand("sma", "sma"), ">", RuleFactorOperand("per", "per")),
    )
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"), FactorRef("per"), FactorRef("rsi")),  # rsi 잉여
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    result = validate_definition(defn, resolve_rule=_resolver({"entry_rule": rule}))
    assert not result.ok
    assert any("잉여" in e for e in result.errors)


def test_factor_refs_consistency_via_formula_transitive_reference() -> None:
    base_formula = Formula(
        id="base_metric", name="base", version="1",
        expression=FormulaFactorOperand("rsi", "rsi"),
    )
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(RuleFormulaOperand("base_metric"), ">", RuleFactorOperand("per", "per")),
    )
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("rsi"), FactorRef("per")),
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    result = validate_definition(
        defn,
        resolve_rule=_resolver({"entry_rule": rule}),
        resolve_formula=_resolver({"base_metric": base_formula}),
    )
    assert result.ok


def test_factor_refs_consistency_skipped_when_formula_operand_but_no_formula_resolver() -> None:
    # resolve_formula 없이(check_formula_store=False 완화) rule이 formula 피연산자를 참조하면
    # 전이 집합을 완전히 산출할 수 없으므로 일치 비교를 보류해야 한다(허위 '잉여' 거부 방지).
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(RuleFormulaOperand("base_metric"), ">", RuleFactorOperand("per", "per")),
    )
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("rsi"), FactorRef("per")),
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    result = validate_definition(
        defn, resolve_rule=_resolver({"entry_rule": rule}), resolve_formula=None
    )
    assert result.ok


def test_draft_skips_factor_refs_consistency_even_with_resolver() -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    result = validate_definition(defn, resolve_rule=_resolver({}))
    assert result.ok


def test_resolve_rule_none_skips_existence_and_consistency() -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(),
        rule=RuleBinding(entry=("anything",)),
    )
    result = validate_definition(defn, resolve_rule=None)
    assert result.ok


def test_is_runnable_true_for_roles_with_entry() -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(),
        rule=RuleBinding(entry=("r1",)),
    )
    assert is_runnable(defn)


def test_validate_definition_strict_raises_on_first_error() -> None:
    defn = StrategyDefinition(
        id="MyStrategy", name="x", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    with pytest.raises(DefinitionValidationError):
        validate_definition_strict(defn)
