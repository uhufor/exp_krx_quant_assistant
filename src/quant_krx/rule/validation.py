from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol

from quant_krx._jsonnorm import ValidationResult
from quant_krx.factors import ParamValidationError, UnknownFactorError, get_factor, list_factors
from quant_krx.rule.definition import (
    Composition,
    FactorOperand,
    FormulaOperand,
    Node,
    Operand,
    Predicate,
    Rule,
)
from quant_krx.rule.errors import DefinitionValidationError

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CROSS_OPS = frozenset({"crosses_above", "crosses_below"})


class FormulaLike(Protocol):
    """rule 패키지가 duck typing으로만 소비하는 최소 표면(INV-2, §3.9)."""

    output_column: str


FormulaResolver = Callable[[str], "FormulaLike | None"]


def _is_snake_case(value: str) -> bool:
    return bool(_SNAKE_CASE_RE.match(value))


def _validate_factor_operand(operand: FactorOperand, errors: list[str]) -> None:
    metadata = next((m for m in list_factors() if m.id == operand.factor_id), None)
    if metadata is None:
        available = ", ".join(m.id for m in list_factors()) or "(등록된 팩터 없음)"
        errors.append(f"미존재 factor_id '{operand.factor_id}'. 사용 가능: {available}")
        return
    if operand.column not in metadata.output:
        valid_cols = ", ".join(metadata.output) or "(출력 컬럼 없음)"
        errors.append(
            f"factor '{operand.factor_id}'의 컬럼 '{operand.column}'은 유효하지 않습니다. "
            f"유효 컬럼: {valid_cols}"
        )
    try:
        get_factor(operand.factor_id, **dict(operand.params))
    except (UnknownFactorError, ParamValidationError) as exc:
        errors.append(str(exc))


def _validate_formula_operand(
    operand: FormulaOperand, resolve_formula: FormulaResolver | None, errors: list[str]
) -> None:
    if resolve_formula is None:
        return
    referenced = resolve_formula(operand.formula_id)
    if referenced is None:
        errors.append(f"미존재 formula_id '{operand.formula_id}'을(를) 참조하고 있습니다")
        return
    if operand.column != referenced.output_column:
        errors.append(
            f"formula '{operand.formula_id}'의 컬럼 '{operand.column}'이(가) "
            f"참조 Formula의 output_column '{referenced.output_column}'과 일치하지 않습니다"
        )


def _validate_operand(
    operand: Operand, resolve_formula: FormulaResolver | None, errors: list[str]
) -> None:
    if isinstance(operand, FactorOperand):
        _validate_factor_operand(operand, errors)
    elif isinstance(operand, FormulaOperand):
        _validate_formula_operand(operand, resolve_formula, errors)


def _walk_node(node: Node, resolve_formula: FormulaResolver | None, errors: list[str]) -> None:
    """좌→우 깊이 우선 고정 순회로 오류 순서 결정론(REQ-C3)."""
    if isinstance(node, Predicate):
        if node.operator in _CROSS_OPS:
            operand_kinds = {node.left.kind, node.right.kind}
            if not (operand_kinds & {"factor", "formula"}):
                errors.append(
                    f"'{node.operator}'는 좌/우 중 최소 1개가 factor 또는 formula 피연산자여야 "
                    f"합니다(상수 crosses 상수는 허용되지 않음)"
                )
        _validate_operand(node.left, resolve_formula, errors)
        _validate_operand(node.right, resolve_formula, errors)
    elif isinstance(node, Composition):
        for child in node.operands:
            _walk_node(child, resolve_formula, errors)


def validate_rule(
    rule: Rule,
    *,
    resolve_formula: FormulaResolver | None = None,
) -> ValidationResult:
    """비발생 검증기. 전 오류 수집, 좌→우 깊이 우선 순회로 오류 순서 결정론(REQ-V1~V3)."""
    errors: list[str] = []
    if not _is_snake_case(rule.id):
        errors.append(f"id는 snake_case·비공백이어야 합니다(입력: '{rule.id}')")
    if not rule.name.strip():
        errors.append("name은 비공백이어야 합니다")
    _walk_node(rule.root, resolve_formula, errors)
    return ValidationResult(ok=not errors, errors=tuple(errors))


def validate_rule_strict(rule: Rule, *, resolve_formula: FormulaResolver | None = None) -> None:
    """엄격 변형: 첫 오류에서 DefinitionValidationError raise. 저장 게이트가 소비."""
    result = validate_rule(rule, resolve_formula=resolve_formula)
    if not result.ok:
        raise DefinitionValidationError(result.errors[0])
