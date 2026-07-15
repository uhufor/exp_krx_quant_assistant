from __future__ import annotations

import pytest

from quant_krx._jsonnorm import DefinitionValidationError
from quant_krx.formula.definition import (
    BinaryOp,
    ConstantOperand,
    FactorOperand,
    Formula,
    FormulaOperand,
)
from quant_krx.formula.validation import (
    derive_required_data,
    validate_formula,
    validate_formula_strict,
)


def _store_resolver(store: dict[str, Formula]):
    def resolve(formula_id: str) -> Formula | None:
        return store.get(formula_id)

    return resolve


def test_valid_formula_passes() -> None:
    formula = Formula(
        id="custom_metric",
        name="커스텀 지표",
        version="1",
        expression=FactorOperand("sma", "sma", {"window": 5}),
    )
    result = validate_formula(formula)
    assert result.ok
    assert result.errors == ()


def test_non_snake_case_id_rejected() -> None:
    formula = Formula(id="CustomMetric", name="x", version="1", expression=ConstantOperand(1))
    result = validate_formula(formula)
    assert not result.ok
    assert any("id" in e for e in result.errors)


def test_unknown_factor_reference_rejected_with_hint() -> None:
    formula = Formula(
        id="m1", name="m1", version="1", expression=FactorOperand("no_such_factor", "x")
    )
    result = validate_formula(formula)
    assert not result.ok
    assert any("no_such_factor" in e and "사용 가능" in e for e in result.errors)


def test_column_not_in_output_rejected_with_hint() -> None:
    formula = Formula(id="m1", name="m1", version="1", expression=FactorOperand("sma", "wrong_col"))
    result = validate_formula(formula)
    assert not result.ok
    assert any("wrong_col" in e and "유효 컬럼" in e for e in result.errors)


def test_param_range_violation_rejected() -> None:
    formula = Formula(
        id="m1", name="m1", version="1",
        expression=FactorOperand("sma", "sma", {"window": -1}),
    )
    result = validate_formula(formula)
    assert not result.ok


def test_param_unknown_name_rejected() -> None:
    formula = Formula(
        id="m1", name="m1", version="1",
        expression=FactorOperand("sma", "sma", {"unknown_param": 1}),
    )
    result = validate_formula(formula)
    assert not result.ok


def test_cross_constraint_validate_params_hook_rejected() -> None:
    formula = Formula(
        id="m1", name="m1", version="1",
        expression=FactorOperand("macd", "macd", {"fast": 30, "slow": 10}),
    )
    result = validate_formula(formula)
    assert not result.ok


def test_cross_constraint_validate_params_hook_passes_valid_override() -> None:
    formula = Formula(
        id="m1", name="m1", version="1",
        expression=FactorOperand("macd", "macd", {"fast": 5, "slow": 10}),
    )
    result = validate_formula(formula)
    assert result.ok


def test_formula_reference_missing_rejected() -> None:
    formula = Formula(id="m1", name="m1", version="1", expression=FormulaOperand("no_such"))
    result = validate_formula(formula, resolve_formula=_store_resolver({}))
    assert not result.ok
    assert any("no_such" in e for e in result.errors)


def test_formula_reference_column_mismatch_rejected() -> None:
    base = Formula(
        id="base", name="base", version="1", expression=ConstantOperand(1), output_column="foo"
    )
    formula = Formula(id="m1", name="m1", version="1", expression=FormulaOperand("base", "bar"))
    store = {"base": base}
    result = validate_formula(formula, resolve_formula=_store_resolver(store))
    assert not result.ok
    assert any("bar" in e for e in result.errors)


def test_formula_reference_valid_passes() -> None:
    base = Formula(
        id="base", name="base", version="1", expression=ConstantOperand(1), output_column="foo"
    )
    formula = Formula(id="m1", name="m1", version="1", expression=FormulaOperand("base", "foo"))
    store = {"base": base}
    result = validate_formula(formula, resolve_formula=_store_resolver(store))
    assert result.ok


def test_resolve_formula_none_skips_formula_and_cycle_checks() -> None:
    formula = Formula(id="m1", name="m1", version="1", expression=FormulaOperand("dangling"))
    result = validate_formula(formula, resolve_formula=None)
    assert result.ok


def test_self_reference_cycle_rejected() -> None:
    formula = Formula(id="m1", name="m1", version="1", expression=FormulaOperand("m1"))
    store = {"m1": formula}
    result = validate_formula(formula, resolve_formula=_store_resolver(store))
    assert not result.ok
    assert any("순환" in e for e in result.errors)


def test_two_cycle_rejected() -> None:
    f1 = Formula(id="f1", name="f1", version="1", expression=FormulaOperand("f2"))
    f2 = Formula(id="f2", name="f2", version="1", expression=FormulaOperand("f1"))
    store = {"f1": f1, "f2": f2}
    result = validate_formula(f1, resolve_formula=_store_resolver(store))
    assert not result.ok
    assert any("순환" in e for e in result.errors)


def test_long_cycle_rejected() -> None:
    f1 = Formula(id="f1", name="f1", version="1", expression=FormulaOperand("f2"))
    f2 = Formula(id="f2", name="f2", version="1", expression=FormulaOperand("f3"))
    f3 = Formula(id="f3", name="f3", version="1", expression=FormulaOperand("f1"))
    store = {"f1": f1, "f2": f2, "f3": f3}
    result = validate_formula(f1, resolve_formula=_store_resolver(store))
    assert not result.ok
    assert any("순환" in e for e in result.errors)


def test_diamond_dag_passes() -> None:
    base = Formula(id="base", name="base", version="1", expression=ConstantOperand(1))
    left = Formula(id="left", name="left", version="1", expression=FormulaOperand("base"))
    right = Formula(id="right", name="right", version="1", expression=FormulaOperand("base"))
    top = Formula(
        id="top", name="top", version="1",
        expression=BinaryOp(op="+", left=FormulaOperand("left"), right=FormulaOperand("right")),
    )
    store = {"base": base, "left": left, "right": right, "top": top}
    result = validate_formula(top, resolve_formula=_store_resolver(store))
    assert result.ok


def test_validate_formula_strict_raises_on_first_error() -> None:
    formula = Formula(id="CustomMetric", name="x", version="1", expression=ConstantOperand(1))
    with pytest.raises(DefinitionValidationError):
        validate_formula_strict(formula)


def test_derive_required_data_transitive_union() -> None:
    base = Formula(id="base", name="base", version="1", expression=FactorOperand("sma", "sma"))
    top = Formula(
        id="top", name="top", version="1",
        expression=BinaryOp(
            op="+",
            left=FormulaOperand("base"),
            right=FactorOperand("per", "per"),
        ),
    )
    store = {"base": base, "top": top}
    required = derive_required_data(top, _store_resolver(store))
    assert set(required) == {"ohlcv", "valuation"}
