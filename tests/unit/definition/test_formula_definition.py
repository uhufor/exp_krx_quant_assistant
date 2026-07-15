from __future__ import annotations

import dataclasses

import pytest

from quant_krx._jsonnorm import MalformedDefinitionError, SchemaVersionError
from quant_krx.formula.definition import (
    BinaryOp,
    ConstantOperand,
    FactorOperand,
    Formula,
    FormulaOperand,
    UnaryOp,
    expr_from_dict,
)


def _nested_formula() -> Formula:
    # (sma_5 * 2.0) + neg(per) — 중첩 표현 트리
    expr = BinaryOp(
        op="+",
        left=BinaryOp(
            op="*", left=FactorOperand("sma", "sma_5", {"window": 5}), right=ConstantOperand(2.0)
        ),
        right=UnaryOp(op="neg", operand=FactorOperand("per", "per")),
    )
    return Formula(
        id="custom_metric", name="커스텀 지표", version="1",
        expression=expr, metadata={"note": "test"},
    )


def test_roundtrip_nested_tree() -> None:
    formula = _nested_formula()
    restored = Formula.from_dict(formula.to_dict())
    assert restored == formula


def test_to_json_twice_is_byte_identical() -> None:
    from quant_krx._jsonnorm import canonical_json

    formula = _nested_formula()
    first = canonical_json(formula.to_dict())
    second = canonical_json(formula.to_dict())
    assert first == second


def test_canonical_eq_distinguishes_int_and_float_constant() -> None:
    f_int = Formula(id="f1", name="f1", version="1", expression=ConstantOperand(30))
    f_float = Formula(id="f1", name="f1", version="1", expression=ConstantOperand(30.0))
    assert len({f_int, f_float}) == 2


def test_frozen_field_assignment_raises() -> None:
    formula = _nested_formula()
    with pytest.raises(dataclasses.FrozenInstanceError):
        formula.name = "변경 시도"  # type: ignore[misc]


def test_future_schema_version_rejected() -> None:
    formula = _nested_formula()
    body = formula.to_dict()
    body["schema_version"] = 999
    with pytest.raises(SchemaVersionError):
        Formula.from_dict(body)


def test_formula_operand_column_missing_defaults_to_value() -> None:
    body = {"kind": "formula", "formula_id": "other"}
    operand = expr_from_dict(body)
    assert isinstance(operand, FormulaOperand)
    assert operand.column == "value"


def test_unknown_operator_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        BinaryOp(op="%", left=ConstantOperand(1), right=ConstantOperand(2))


def test_unknown_unary_operator_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        UnaryOp(op="abs", operand=ConstantOperand(1))


def test_binary_op_missing_left_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        expr_from_dict({"node": "binary", "op": "+", "right": {"kind": "constant", "value": 1}})


def test_unknown_node_tag_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        expr_from_dict({"node": "ternary"})


def test_unknown_kind_tag_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        expr_from_dict({"kind": "unknown"})


def test_missing_tag_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        expr_from_dict({"op": "+"})


def test_duplicate_tag_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        expr_from_dict({"node": "binary", "kind": "factor"})


def test_constant_operand_rejects_bool() -> None:
    with pytest.raises(MalformedDefinitionError):
        ConstantOperand(True)  # noqa: FBT003


def test_constant_operand_rejects_nan_and_inf() -> None:
    with pytest.raises(MalformedDefinitionError):
        ConstantOperand(float("nan"))
    with pytest.raises(MalformedDefinitionError):
        ConstantOperand(float("inf"))


def test_factor_operand_params_normalized_tuple_to_list_roundtrip() -> None:
    operand = FactorOperand("sma", "sma_5", params={"window": 5})
    restored = FactorOperand.from_dict(operand.to_dict())
    assert restored == operand
