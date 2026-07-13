from __future__ import annotations

import dataclasses

import pytest

import quant_krx.formula.definition as formula_definition
from quant_krx._jsonnorm import MalformedDefinitionError, SchemaVersionError
from quant_krx.rule.definition import (
    Composition,
    ConstantOperand,
    FactorOperand,
    FormulaOperand,
    Predicate,
    Rule,
    node_from_dict,
)


def _nested_rule() -> Rule:
    # (sma_5 > per) AND NOT(rsi < 30)
    root = Composition(
        op="AND",
        operands=(
            Predicate(
                left=FactorOperand("sma", "sma"), operator=">", right=FactorOperand("per", "per")
            ),
            Composition(
                op="NOT",
                operands=(
                    Predicate(
                        left=FactorOperand("rsi", "rsi"), operator="<", right=ConstantOperand(30)
                    ),
                ),
            ),
        ),
    )
    return Rule(id="entry_rule", name="진입 규칙", version="1", root=root)


def test_roundtrip_nested_tree() -> None:
    rule = _nested_rule()
    assert Rule.from_dict(rule.to_dict()) == rule


def test_frozen_field_assignment_raises() -> None:
    rule = _nested_rule()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.name = "변경 시도"  # type: ignore[misc]


def test_future_schema_version_rejected() -> None:
    rule = _nested_rule()
    body = rule.to_dict()
    body["schema_version"] = 999
    with pytest.raises(SchemaVersionError):
        Rule.from_dict(body)


def test_and_requires_at_least_two_operands() -> None:
    with pytest.raises(MalformedDefinitionError):
        Composition(
            op="AND", operands=(Predicate(FactorOperand("sma", "sma"), ">", ConstantOperand(1)),)
        )


def test_not_requires_exactly_one_operand() -> None:
    p = Predicate(FactorOperand("sma", "sma"), ">", ConstantOperand(1))
    with pytest.raises(MalformedDefinitionError):
        Composition(op="NOT", operands=(p, p))


def test_unknown_logical_operator_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        Composition(op="XOR", operands=(ConstantOperand(1), ConstantOperand(2)))


def test_unknown_comparison_operator_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        Predicate(FactorOperand("sma", "sma"), "~=", ConstantOperand(1))


def test_unknown_operand_kind_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        node_from_dict({
            "node": "predicate",
            "left": {"kind": "bogus"},
            "operator": ">",
            "right": {"kind": "constant", "value": 1},
        })


def test_unknown_node_tag_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        node_from_dict({"node": "ternary"})


def test_missing_node_tag_rejected() -> None:
    with pytest.raises(MalformedDefinitionError):
        node_from_dict({"op": "AND"})


def test_constant_operand_rejects_bool() -> None:
    with pytest.raises(MalformedDefinitionError):
        ConstantOperand(True)  # noqa: FBT003


def test_rule_formula_operand_is_independent_of_formula_package() -> None:
    # rule.FormulaOperand는 formula.FormulaOperand와 완전 별개 클래스(INV-2)
    assert FormulaOperand is not formula_definition.FormulaOperand
    operand = FormulaOperand("some_formula")
    assert operand.column == "value"
    restored = FormulaOperand.from_dict(operand.to_dict())
    assert restored == operand
