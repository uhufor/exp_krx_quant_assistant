from __future__ import annotations

import pytest

from quant_krx._jsonnorm import DefinitionValidationError
from quant_krx.rule.definition import (
    Composition,
    ConstantOperand,
    FactorOperand,
    FormulaOperand,
    Predicate,
    Rule,
)
from quant_krx.rule.validation import validate_rule, validate_rule_strict


def _dummy_formula(output_column: str = "value"):
    class _F:
        pass

    f = _F()
    f.output_column = output_column
    return f


def test_valid_rule_passes() -> None:
    rule = Rule(
        id="entry_rule", name="진입", version="1",
        root=Predicate(FactorOperand("sma", "sma"), ">", FactorOperand("per", "per")),
    )
    result = validate_rule(rule)
    assert result.ok


def test_non_snake_case_id_rejected() -> None:
    rule = Rule(
        id="EntryRule", name="x", version="1",
        root=Predicate(ConstantOperand(1), ">", ConstantOperand(2)),
    )
    result = validate_rule(rule)
    assert not result.ok


def test_unknown_factor_reference_rejected() -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(FactorOperand("no_such", "x"), ">", ConstantOperand(1)),
    )
    result = validate_rule(rule)
    assert not result.ok
    assert any("no_such" in e for e in result.errors)


def test_column_not_in_output_rejected() -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(FactorOperand("sma", "wrong"), ">", ConstantOperand(1)),
    )
    result = validate_rule(rule)
    assert not result.ok


def test_macd_cross_constraint_violation_rejected() -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(
            FactorOperand("macd", "macd", {"fast": 30, "slow": 5}), ">", ConstantOperand(0)
        ),
    )
    result = validate_rule(rule)
    assert not result.ok


def test_constant_crosses_constant_rejected() -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(ConstantOperand(1), "crosses_above", ConstantOperand(2)),
    )
    result = validate_rule(rule)
    assert not result.ok
    assert any("crosses_above" in e for e in result.errors)


def test_factor_crosses_constant_passes_structural_guard() -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(FactorOperand("sma", "sma"), "crosses_above", ConstantOperand(100)),
    )
    result = validate_rule(rule)
    assert result.ok


def test_formula_operand_missing_reference_rejected() -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(FormulaOperand("no_formula"), ">", ConstantOperand(1)),
    )
    result = validate_rule(rule, resolve_formula=lambda fid: None)
    assert not result.ok
    assert any("no_formula" in e for e in result.errors)


def test_formula_operand_column_mismatch_rejected() -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(FormulaOperand("base", "wrong_col"), ">", ConstantOperand(1)),
    )
    result = validate_rule(rule, resolve_formula=lambda fid: _dummy_formula("value"))
    assert not result.ok


def test_formula_operand_valid_reference_passes() -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(FormulaOperand("base", "value"), ">", ConstantOperand(1)),
    )
    result = validate_rule(rule, resolve_formula=lambda fid: _dummy_formula("value"))
    assert result.ok


def test_nested_composition_error_order_is_deterministic() -> None:
    root = Composition(
        op="AND",
        operands=(
            Predicate(FactorOperand("no_such_a", "x"), ">", ConstantOperand(1)),
            Predicate(FactorOperand("no_such_b", "y"), ">", ConstantOperand(1)),
        ),
    )
    rule = Rule(id="r1", name="r1", version="1", root=root)
    result = validate_rule(rule)
    assert not result.ok
    assert "no_such_a" in result.errors[0]
    assert "no_such_b" in result.errors[1]


def test_validate_rule_strict_raises_on_first_error() -> None:
    rule = Rule(
        id="EntryRule", name="x", version="1",
        root=Predicate(ConstantOperand(1), ">", ConstantOperand(2)),
    )
    with pytest.raises(DefinitionValidationError):
        validate_rule_strict(rule)
