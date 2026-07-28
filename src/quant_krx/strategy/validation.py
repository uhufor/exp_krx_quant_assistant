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

    # portfolio.ranking이 참조하는 factor/formula도 실행 시 실제로 평가되므로 전이 집합에
    # 포함한다(P1). 빠뜨리면 ranking용 factor를 factor_refs에 선언했을 때 "잉여"로 거부되고,
    # 선언하지 않으면 실행 시점에야 미존재가 드러난다(불변식 4: 참조 무결성은 저장 시점).
    ranking = defn.portfolio.ranking if defn.portfolio is not None else None
    if ranking is not None:
        if ranking.kind == "factor":
            acc.add(ranking.factor_id)
        elif ranking.kind == "formula":
            if resolve_formula is None:
                incomplete = True
            else:
                seen_formula_ids.add(ranking.formula_id)
                referenced = resolve_formula(ranking.formula_id)
                if referenced is None:
                    errors.append(
                        f"portfolio.ranking이 미존재 formula_id '{ranking.formula_id}'을(를) "
                        "참조하고 있습니다"
                    )
                else:
                    acc |= _collect_formula_factor_ids(
                        referenced, resolve_formula, seen_formula_ids
                    )

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


def _validate_ranking(defn: StrategyDefinition, errors: list[str]) -> None:
    """portfolio.ranking이 참조하는 팩터의 존재·파라미터·컬럼을 저장 시점에 확인한다(P1)."""
    ranking = defn.portfolio.ranking if defn.portfolio is not None else None
    if ranking is None or ranking.kind != "factor":
        return
    metadata = next((m for m in list_factors() if m.id == ranking.factor_id), None)
    if metadata is None:
        available = ", ".join(m.id for m in list_factors()) or "(등록된 팩터 없음)"
        errors.append(
            f"portfolio.ranking의 미존재 factor_id '{ranking.factor_id}'. 사용 가능: {available}"
        )
        return
    try:
        get_factor(ranking.factor_id, **dict(ranking.params))
    except (UnknownFactorError, ParamValidationError) as exc:
        errors.append(f"portfolio.ranking: {exc}")
    if ranking.column not in metadata.output:
        errors.append(
            f"portfolio.ranking의 factor '{ranking.factor_id}'에 컬럼 '{ranking.column}'이"
            f" 없습니다. 사용 가능: {', '.join(metadata.output)}"
        )


def _validate_dynamic_universe(defn: StrategyDefinition, errors: list[str]) -> None:
    """동적(스크리닝) 유니버스는 포트폴리오 모드에서만 의미가 있다(P2, 사용자 확정).

    종목별 독립 백테스트에서는 "시점마다 대상 종목이 바뀐다"는 개념이 성립하지 않는다 —
    종목마다 자기 자본으로 따로 돌기 때문에 교체가 아무 의미도 만들지 않는다. 저장 시점에
    거부해 "설정은 됐는데 실행 결과가 무의미한" 조합을 원천 차단한다.
    """
    if defn.universe.is_dynamic and defn.portfolio is None:
        errors.append(
            "universe.kind='screening'은 portfolio 정책과 함께 사용해야 합니다"
            "(종목별 독립 백테스트에서는 시점별 종목 교체가 의미를 갖지 않습니다)"
        )


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

    _validate_ranking(defn, errors)
    _validate_dynamic_universe(defn, errors)

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
