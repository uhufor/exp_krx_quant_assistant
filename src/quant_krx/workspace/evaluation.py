from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quant_krx._jsonnorm import canonical_json
from quant_krx.factors import (
    FactorInput,
    compute_factor,
    get_factor,
    get_factor_notes,
    list_factors,
)
from quant_krx.formula.definition import BinaryOp, ConstantOperand, Expr, Formula, UnaryOp
from quant_krx.formula.definition import FactorOperand as FormulaFactorOperand
from quant_krx.formula.definition import FormulaOperand as FormulaFormulaOperand
from quant_krx.formula.validation import derive_required_data
from quant_krx.rule.definition import Composition, Node, Operand, Predicate, Rule
from quant_krx.rule.definition import ConstantOperand as RuleConstantOperand
from quant_krx.rule.definition import FactorOperand as RuleFactorOperand
from quant_krx.rule.definition import FormulaOperand as RuleFormulaOperand
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.workspace import numeric
from quant_krx.workspace.errors import EvaluationError, MissingDataError

FormulaResolver = Callable[[str], "Formula | None"]
RuleResolver = Callable[[str], "Rule | None"]

_CROSS_OPERATORS = frozenset({"crosses_above", "crosses_below"})


@dataclass
class EvaluationContext:
    """단일 (전략, 종목) 평가 컨텍스트 — 캐시 소유(C3-i). 컨텍스트 종료 시 캐시는 GC로 폐기."""

    data: FactorInput
    index: pd.DatetimeIndex
    resolve_formula: FormulaResolver
    resolve_rule: RuleResolver | None = None
    _factor_cache: dict[tuple[str, str, str], pd.Series] = field(default_factory=dict)
    _formula_cache: dict[str, pd.Series] = field(default_factory=dict)
    _visiting: set[str] = field(default_factory=set)


def _factor_metadata(factor_id: str):
    return next((m for m in list_factors() if m.id == factor_id), None)


def _eval_factor_operand(
    factor_id: str, column: str, params: dict[str, Any], ctx: EvaluationContext
) -> pd.Series:
    """캐시 키 (factor_id, column, canonical(params)) — 동일 팩터·상이 파라미터는 별개 시계열(D1),
    동일 팩터·동일 파라미터라도 상이 컬럼(예: macd의 macd/signal, bollinger의 lower/middle)은
    별개 시계열이어야 하므로 column을 키에 포함한다(column 누락 시 다른 컬럼 참조가 캐시를
    오염시켜 크로스 신호가 항상 0이 되는 버그가 있었음)."""
    key = (factor_id, column, canonical_json(params))
    cached = ctx._factor_cache.get(key)
    if cached is not None:
        return cached
    factor = get_factor(factor_id, **params)
    result_df = compute_factor(factor, ctx.data)
    get_factor_notes(result_df)  # 반환 직후 판독(R01 advisory 계약 준수)
    series = numeric.align(result_df[column], ctx.index)
    ctx._factor_cache[key] = series
    return series


def evaluate_formula(formula: Formula, ctx: EvaluationContext) -> pd.Series:
    """산술 트리 재귀 평가 → pd.Series(기준 인덱스 정렬)."""
    return _eval_formula_expr(formula.expression, ctx)


def _eval_formula_expr(expr: Expr, ctx: EvaluationContext) -> pd.Series:
    if isinstance(expr, BinaryOp):
        left = _eval_formula_expr(expr.left, ctx)
        right = _eval_formula_expr(expr.right, ctx)
        return numeric.binary_arith(expr.op, left, right)
    if isinstance(expr, UnaryOp):
        return -_eval_formula_expr(expr.operand, ctx)
    if isinstance(expr, FormulaFactorOperand):
        return _eval_factor_operand(expr.factor_id, expr.column, dict(expr.params), ctx)
    if isinstance(expr, ConstantOperand):
        return numeric.broadcast(float(expr.value), ctx.index)
    if isinstance(expr, FormulaFormulaOperand):
        return _eval_formula_ref(expr.formula_id, ctx)
    raise EvaluationError(f"미지의 Formula 표현식입니다: {expr!r}")


def _eval_formula_ref(formula_id: str, ctx: EvaluationContext) -> pd.Series:
    if formula_id in ctx._formula_cache:
        return ctx._formula_cache[formula_id]
    if formula_id in ctx._visiting:
        raise EvaluationError(f"Formula 순환 참조가 발견되었습니다: {formula_id}")
    referenced = ctx.resolve_formula(formula_id)
    if referenced is None:
        raise EvaluationError(f"미존재 formula_id '{formula_id}'을(를) 참조하고 있습니다")
    ctx._visiting.add(formula_id)
    try:
        series = _eval_formula_expr(referenced.expression, ctx)
    finally:
        ctx._visiting.discard(formula_id)
    ctx._formula_cache[formula_id] = series
    return series


def evaluate_rule(rule: Rule, ctx: EvaluationContext) -> pd.Series:
    """Predicate/Composition 태그 순회 평가 → pd.Series(dtype=bool)."""
    return _eval_rule_node(rule.root, ctx)


def _eval_rule_node(node: Node, ctx: EvaluationContext) -> pd.Series:
    if isinstance(node, Predicate):
        left = _eval_rule_operand(node.left, ctx)
        right = _eval_rule_operand(node.right, ctx)
        if node.operator in _CROSS_OPERATORS:
            return numeric.crosses(node.operator, left, right)
        return numeric.compare(node.operator, left, right)
    if isinstance(node, Composition):
        children = [_eval_rule_node(child, ctx) for child in node.operands]
        if node.op == "AND":
            result = children[0]
            for child in children[1:]:
                result = result & child
            return result
        if node.op == "OR":
            result = children[0]
            for child in children[1:]:
                result = result | child
            return result
        return ~children[0]  # NOT
    raise EvaluationError(f"미지의 Rule 노드입니다: {node!r}")


def _eval_rule_operand(operand: Operand, ctx: EvaluationContext) -> pd.Series:
    if isinstance(operand, RuleFactorOperand):
        return _eval_factor_operand(operand.factor_id, operand.column, dict(operand.params), ctx)
    if isinstance(operand, RuleConstantOperand):
        return numeric.broadcast(float(operand.value), ctx.index)
    if isinstance(operand, RuleFormulaOperand):
        return _eval_formula_ref(operand.formula_id, ctx)
    raise EvaluationError(f"미지의 Rule 피연산자입니다: {operand!r}")


def _rule_leaf_operands(node: Node) -> list[Operand]:
    if isinstance(node, Predicate):
        return [node.left, node.right]
    if isinstance(node, Composition):
        leaves: list[Operand] = []
        for child in node.operands:
            leaves.extend(_rule_leaf_operands(child))
        return leaves
    return []


def _required_data_by_kind(
    defn: StrategyDefinition, resolve_rule: RuleResolver, resolve_formula: FormulaResolver
) -> dict[str, set[str]]:
    """factor_refs 직접분 + rule 전이 참조 factor/formula의 required_data를 kind별로 집계."""
    by_kind: dict[str, set[str]] = {}

    def add(kind: str, id_: str) -> None:
        by_kind.setdefault(kind, set()).add(id_)

    for factor_ref in defn.factor_refs:
        metadata = _factor_metadata(factor_ref.factor_id)
        if metadata is not None:
            for kind in metadata.required_data:
                add(kind, factor_ref.factor_id)

    if defn.rule is not None:
        for rule_id in tuple(defn.rule.entry) + tuple(defn.rule.exit):
            rule = resolve_rule(rule_id)
            if rule is None:
                continue
            for operand in _rule_leaf_operands(rule.root):
                if isinstance(operand, RuleFactorOperand):
                    metadata = _factor_metadata(operand.factor_id)
                    if metadata is not None:
                        for kind in metadata.required_data:
                            add(kind, operand.factor_id)
                elif isinstance(operand, RuleFormulaOperand):
                    formula = resolve_formula(operand.formula_id)
                    if formula is not None:
                        for kind in derive_required_data(formula, resolve_formula):
                            add(kind, operand.formula_id)

    return by_kind


def strategy_required_data(
    defn: StrategyDefinition, resolve_rule: RuleResolver, resolve_formula: FormulaResolver
) -> frozenset[str]:
    """전략이 전이적으로 참조하는 factor/formula의 required_data 합집합(FR-09)."""
    return frozenset(_required_data_by_kind(defn, resolve_rule, resolve_formula).keys())


def check_data_contract(
    defn: StrategyDefinition, ctx: EvaluationContext, resolve_rule: RuleResolver
) -> None:
    """데이터 계약 게이트 — 미충족 시 MissingDataError(누락 종류 + 요구 id)."""
    by_kind = _required_data_by_kind(defn, resolve_rule, ctx.resolve_formula)
    for kind in ("valuation", "financials"):
        if kind in by_kind and getattr(ctx.data, kind) is None:
            raise MissingDataError(kind, tuple(sorted(by_kind[kind])))
