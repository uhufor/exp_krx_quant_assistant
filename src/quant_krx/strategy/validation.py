from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from quant_krx._jsonnorm import ValidationResult
from quant_krx.factors import ParamValidationError, UnknownFactorError, get_factor, list_factors
from quant_krx.strategy.definition import FactorRef, StrategyDefinition
from quant_krx.strategy.errors import DefinitionValidationError

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class RuleLike(Protocol):
    """duck typing 최소 표면(INV-2) — rule 패키지를 import하지 않고 태그 속성만 소비."""

    root: Any


class FormulaLike(Protocol):
    """duck typing 최소 표면(INV-2) — formula 패키지를 import하지 않고 태그 속성만 소비."""

    output_column: str
    expression: Any


RuleResolver = Callable[[str], "RuleLike | None"]
FormulaResolver = Callable[[str], "FormulaLike | None"]


def _is_snake_case(value: str) -> bool:
    return bool(_SNAKE_CASE_RE.match(value))


def _walk_rule_operands(node: Any) -> Iterator[Any]:
    """duck-typed Rule Node 트리 순회 — rule 패키지 미참조, 태그 속성(.node/.left 등)만 사용."""
    node_tag = getattr(node, "node", None)
    if node_tag == "predicate":
        yield node.left
        yield node.right
    elif node_tag == "composition":
        for child in node.operands:
            yield from _walk_rule_operands(child)


def _walk_formula_leaves(expr: Any) -> Iterator[Any]:
    """duck-typed Formula Expr 순회 — formula 패키지 미참조, 태그 속성(.node/.left 등)만 사용."""
    node_tag = getattr(expr, "node", None)
    if node_tag == "binary":
        yield from _walk_formula_leaves(expr.left)
        yield from _walk_formula_leaves(expr.right)
    elif node_tag == "unary":
        yield from _walk_formula_leaves(expr.operand)
    else:
        yield expr


def _collect_formula_factor_ids(
    formula_like: FormulaLike,
    resolve_formula: FormulaResolver | None,
    seen_formula_ids: set[str],
) -> set[str]:
    acc: set[str] = set()
    for leaf in _walk_formula_leaves(formula_like.expression):
        kind = getattr(leaf, "kind", None)
        if kind == "factor":
            acc.add(leaf.factor_id)
        elif kind == "formula" and resolve_formula is not None:
            fid = leaf.formula_id
            if fid in seen_formula_ids:
                continue
            seen_formula_ids.add(fid)
            referenced = resolve_formula(fid)
            if referenced is not None:
                acc |= _collect_formula_factor_ids(referenced, resolve_formula, seen_formula_ids)
    return acc


def _transitive_factor_ids(
    defn: StrategyDefinition,
    resolve_rule: RuleResolver,
    resolve_formula: FormulaResolver | None,
) -> tuple[set[str], list[str], bool]:
    """rule 슬롯이 전이 참조하는 factor id 집합 산출.

    반환: (집합, 오류 메시지 목록, incomplete). formula 피연산자를 만났으나
    resolve_formula가 주입되지 않아 전이 확장을 할 수 없었으면 incomplete=True —
    호출부는 이 경우 불완전한 집합을 기준으로 한 일치 비교를 보류해야 한다(TR-R02-011).
    """
    assert defn.rule is not None
    acc: set[str] = set()
    errors: list[str] = []
    incomplete = False
    seen_formula_ids: set[str] = set()
    rule_ids = tuple(defn.rule.entry) + tuple(defn.rule.exit)
    for rule_id in rule_ids:
        rule = resolve_rule(rule_id)
        if rule is None:
            errors.append(f"미존재 rule_id '{rule_id}'을(를) 참조하고 있습니다")
            continue
        for operand in _walk_rule_operands(rule.root):
            kind = getattr(operand, "kind", None)
            if kind == "factor":
                acc.add(operand.factor_id)
            elif kind == "formula":
                if resolve_formula is None:
                    incomplete = True
                    continue
                fid = operand.formula_id
                if fid in seen_formula_ids:
                    continue
                seen_formula_ids.add(fid)
                referenced = resolve_formula(fid)
                if referenced is not None:
                    acc |= _collect_formula_factor_ids(
                        referenced, resolve_formula, seen_formula_ids
                    )
    return acc, errors, incomplete


def _validate_factor_ref(factor_ref: FactorRef, errors: list[str]) -> None:
    metadata = next((m for m in list_factors() if m.id == factor_ref.factor_id), None)
    if metadata is None:
        available = ", ".join(m.id for m in list_factors()) or "(등록된 팩터 없음)"
        errors.append(f"미존재 factor_id '{factor_ref.factor_id}'. 사용 가능: {available}")
        return
    try:
        get_factor(factor_ref.factor_id, **dict(factor_ref.params))
    except (UnknownFactorError, ParamValidationError) as exc:
        errors.append(str(exc))


def validate_definition(
    defn: StrategyDefinition,
    *,
    resolve_rule: RuleResolver | None = None,
    resolve_formula: FormulaResolver | None = None,
) -> ValidationResult:
    """비발생 검증기. 전 오류 수집, 순서 결정론(REQ-V1~V3)."""
    errors: list[str] = []

    if not _is_snake_case(defn.id):
        errors.append(f"id는 snake_case·비공백이어야 합니다(입력: '{defn.id}')")
    if not defn.name.strip():
        errors.append("name은 비공백이어야 합니다")

    for factor_ref in defn.factor_refs:
        _validate_factor_ref(factor_ref, errors)

    if defn.rule is not None and resolve_rule is not None:
        transitive, walk_errors, incomplete = _transitive_factor_ids(
            defn, resolve_rule, resolve_formula
        )
        errors.extend(walk_errors)
        if not walk_errors and not incomplete:
            declared = {fr.factor_id for fr in defn.factor_refs}
            missing = transitive - declared
            extra = declared - transitive
            if missing or extra:
                hints = []
                if missing:
                    hints.append(f"누락: {sorted(missing)}")
                if extra:
                    hints.append(f"잉여: {sorted(extra)}")
                errors.append(
                    "factor_refs가 rule의 전이 참조 factor 집합과 일치하지 않습니다"
                    f"({', '.join(hints)})"
                )

    return ValidationResult(ok=not errors, errors=tuple(errors))


def validate_definition_strict(
    defn: StrategyDefinition,
    *,
    resolve_rule: RuleResolver | None = None,
    resolve_formula: FormulaResolver | None = None,
) -> None:
    """엄격 변형: 첫 오류에서 DefinitionValidationError raise. 저장 게이트가 소비."""
    result = validate_definition(defn, resolve_rule=resolve_rule, resolve_formula=resolve_formula)
    if not result.ok:
        raise DefinitionValidationError(result.errors[0])


def is_runnable(defn: StrategyDefinition) -> bool:
    """rule 슬롯이 roles 형상이고 entry>=1이면 True(D4). 소비자: PRD-R03 §4."""
    return defn.rule is not None and len(defn.rule.entry) >= 1
