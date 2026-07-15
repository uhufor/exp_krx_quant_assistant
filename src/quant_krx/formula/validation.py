from __future__ import annotations

import re
from collections.abc import Callable

from quant_krx._jsonnorm import ValidationResult
from quant_krx.factors import ParamValidationError, UnknownFactorError, get_factor, list_factors
from quant_krx.formula.definition import (
    BinaryOp,
    Expr,
    FactorOperand,
    Formula,
    FormulaOperand,
    UnaryOp,
)
from quant_krx.formula.errors import DefinitionValidationError

FormulaResolver = Callable[[str], "Formula | None"]

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_GRAY = 1
_BLACK = 2


def _is_snake_case(value: str) -> bool:
    return bool(_SNAKE_CASE_RE.match(value))


def _leaf_operands(expr: Expr) -> list[Expr]:
    """표현 트리를 좌→우 깊이 우선으로 순회해 리프 피연산자만 수집(오류 순서 결정론, REQ-C3)."""
    if isinstance(expr, BinaryOp):
        return _leaf_operands(expr.left) + _leaf_operands(expr.right)
    if isinstance(expr, UnaryOp):
        return _leaf_operands(expr.operand)
    return [expr]


def _formula_ids_referenced(expr: Expr) -> tuple[str, ...]:
    return tuple(op.formula_id for op in _leaf_operands(expr) if isinstance(op, FormulaOperand))


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


def _detect_cycle(root: Formula, resolve_formula: FormulaResolver) -> tuple[str, ...] | None:
    """DFS gray/black 순환 검출. root는 store에 없을 수 있어 expression을 직접 시드한다(§6.2)."""
    color: dict[str, int] = {}
    path: list[str] = []

    def visit(formula_id: str, expr: Expr) -> tuple[str, ...] | None:
        color[formula_id] = _GRAY
        path.append(formula_id)
        for ref_id in _formula_ids_referenced(expr):
            if color.get(ref_id) == _GRAY:
                cycle_start = path.index(ref_id)
                return tuple(path[cycle_start:] + [ref_id])
            if color.get(ref_id) != _BLACK:
                referenced = resolve_formula(ref_id)
                if referenced is not None:
                    result = visit(ref_id, referenced.expression)
                    if result is not None:
                        return result
        color[formula_id] = _BLACK
        path.pop()
        return None

    return visit(root.id, root.expression)


def validate_formula(
    formula: Formula,
    *,
    resolve_formula: FormulaResolver | None = None,
) -> ValidationResult:
    """비발생 검증기. 전 오류 수집, 좌→우 깊이 우선 순회로 오류 순서 결정론(REQ-V1~V3)."""
    errors: list[str] = []

    if not _is_snake_case(formula.id):
        errors.append(f"id는 snake_case·비공백이어야 합니다(입력: '{formula.id}')")
    if not formula.name.strip():
        errors.append("name은 비공백이어야 합니다")
    if not _is_snake_case(formula.output_column):
        errors.append(
            f"output_column은 snake_case·비공백이어야 합니다(입력: '{formula.output_column}')"
        )

    # 자기참조가 "미존재 참조"로 오판되지 않도록 순환 검출을 참조 존재 확인보다 먼저 수행한다.
    if resolve_formula is not None:
        cycle = _detect_cycle(formula, resolve_formula)
        if cycle is not None:
            errors.append(f"순환 참조가 발견되었습니다: {' -> '.join(cycle)}")

    for operand in _leaf_operands(formula.expression):
        if isinstance(operand, FactorOperand):
            _validate_factor_operand(operand, errors)
        elif isinstance(operand, FormulaOperand):
            _validate_formula_operand(operand, resolve_formula, errors)

    return ValidationResult(ok=not errors, errors=tuple(errors))


def validate_formula_strict(
    formula: Formula, *, resolve_formula: FormulaResolver | None = None
) -> None:
    """엄격 변형: 첫 오류에서 DefinitionValidationError raise. 저장 게이트가 소비."""
    result = validate_formula(formula, resolve_formula=resolve_formula)
    if not result.ok:
        raise DefinitionValidationError(result.errors[0])


def derive_required_data(formula: Formula, resolve_formula: FormulaResolver) -> tuple[str, ...]:
    """참조 factor들의 required_data를 전이 합집합으로 파생한다(저장 필드 아님)."""
    seen_formulas: set[str] = set()
    required: set[str] = set()

    def walk(expr: Expr) -> None:
        for operand in _leaf_operands(expr):
            if isinstance(operand, FactorOperand):
                metadata = next((m for m in list_factors() if m.id == operand.factor_id), None)
                if metadata is not None:
                    required.update(metadata.required_data)
            elif isinstance(operand, FormulaOperand):
                if operand.formula_id in seen_formulas:
                    continue
                seen_formulas.add(operand.formula_id)
                referenced = resolve_formula(operand.formula_id)
                if referenced is not None:
                    walk(referenced.expression)

    walk(formula.expression)
    return tuple(sorted(required))
