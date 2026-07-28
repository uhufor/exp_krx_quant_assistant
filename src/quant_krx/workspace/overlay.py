"""파라미터 오버레이(P4) — 저장된 정의를 건드리지 않고 파생 정의를 만든다.

파라미터 스윕은 같은 전략을 값만 바꿔 수십 번 돌리는 일이다. 저장된 정의를 고쳤다 되돌리면
중간에 실패했을 때 원본이 오염되고, 활성 참조 보호(FR-04a)와도 충돌한다. 그래서 여기서는
**메모리 상의 파생 정의와 리졸버 래퍼**만 만들고 DB는 일절 건드리지 않는다.

주소 문법(화이트리스트, fail-closed):

| 키 | 대상 | 예 |
|---|---|---|
| `portfolio.<field>` | `PortfolioPolicy` 필드 | `portfolio.max_positions` |
| `factor.<factor_id>.<param>` | 팩터가 **참조되는 모든 곳**의 params | `factor.momentum.window` |
| `factor.<factor_id>@<현재값>.<param>` | 그 값을 쓰는 참조만 | `factor.sma@5.window` |
| `rule.<rule_id>.threshold` | 단일 Predicate 룰의 상수 임계값 | `rule.per_rule.threshold` |

`factor.*`가 "모든 곳"인 이유: 실행 시 실제로 쓰이는 파라미터는 `factor_refs`가 아니라
Rule/Formula 피연산자와 `portfolio.ranking`에 적힌 값이다(`evaluation.py::_eval_factor_operand`).
`factor_refs`만 바꾸면 저장은 되는데 계산은 그대로인 **조용한 무효 스윕**이 된다.

`@<현재값>` 선택자가 필요한 이유: 골든크로스처럼 **같은 팩터를 서로 다른 파라미터로 두 번
쓰는** 전략이 흔하다. 선택자 없이 `factor.sma.window`를 스윕하면 단기·장기 창이 같은 값이
되어 신호가 영영 발생하지 않는다(조용히 성과 0). `factor.sma@5.window`는 현재 `window`가
5인 참조만 바꾼다.
"""

from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from quant_krx.formula.definition import BinaryOp, Expr, Formula, UnaryOp
from quant_krx.formula.definition import FactorOperand as FormulaFactorOperand
from quant_krx.rule.definition import Composition, Node, Predicate, Rule
from quant_krx.rule.definition import ConstantOperand as RuleConstantOperand
from quant_krx.rule.definition import FactorOperand as RuleFactorOperand
from quant_krx.strategy.definition import StrategyDefinition

PORTFOLIO_FIELDS = ("max_positions", "rebalance", "sizing", "initial_cash")
RULE_SUFFIX = "threshold"

# 정수여야 하는 포트폴리오 필드 — JSON에서 5.0으로 들어와도 dataclass 검증을 통과하도록 캐스팅.
_INT_PORTFOLIO_FIELDS = frozenset({"max_positions"})
_FLOAT_PORTFOLIO_FIELDS = frozenset({"initial_cash"})


class OverlayError(ValueError):
    """오버레이 키 형식 오류 또는 적용 불가능한 대상."""


@dataclass(frozen=True)
class FactorTarget:
    """어떤 팩터 참조의 어떤 파라미터를 바꿀지.

    `selector`가 비어 있으면 그 팩터의 모든 참조가 대상이고, 값이 있으면 해당 파라미터가
    현재 그 값인 참조만 대상이다(`factor.sma@5.window`).
    """

    factor_id: str
    param: str
    selector: str = ""

    def matches(self, factor_id: str, params: Mapping[str, Any]) -> bool:
        if factor_id != self.factor_id:
            return False
        if not self.selector:
            return True
        return str(params.get(self.param)) == self.selector


@dataclass(frozen=True)
class Overlay:
    """파싱된 오버레이 — 어디에 무엇을 덮어쓸지의 구조화된 표현."""

    portfolio: Mapping[str, Any] = field(default_factory=dict)
    factor_params: Mapping[FactorTarget, Any] = field(default_factory=dict)
    rule_thresholds: Mapping[str, float] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.portfolio or self.factor_params or self.rule_thresholds)


def parse_overlay(overrides: Mapping[str, Any]) -> Overlay:
    """`{"portfolio.max_positions": 5, ...}` -> Overlay. 미지의 키는 즉시 거부한다."""
    portfolio: dict[str, Any] = {}
    factor_params: dict[FactorTarget, Any] = {}
    rule_thresholds: dict[str, float] = {}

    for key, value in overrides.items():
        parts = key.split(".")
        if parts[0] == "portfolio" and len(parts) == 2:
            field_name = parts[1]
            if field_name not in PORTFOLIO_FIELDS:
                raise OverlayError(
                    f"미지의 portfolio 필드 '{field_name}'(허용: {list(PORTFOLIO_FIELDS)})"
                )
            if field_name in _INT_PORTFOLIO_FIELDS:
                value = int(value)
            elif field_name in _FLOAT_PORTFOLIO_FIELDS:
                value = float(value)
            portfolio[field_name] = value
        elif parts[0] == "factor" and len(parts) == 3:
            factor_id, _, selector = parts[1].partition("@")
            if not factor_id:
                raise OverlayError(f"오버레이 키 '{key}'에 factor_id가 없습니다")
            factor_params[FactorTarget(factor_id, parts[2], selector)] = value
        elif parts[0] == "rule" and len(parts) == 3:
            if parts[2] != RULE_SUFFIX:
                raise OverlayError(
                    f"룰 오버레이는 '.{RULE_SUFFIX}'만 지원합니다(입력: '{key}')"
                )
            rule_thresholds[parts[1]] = float(value)
        else:
            raise OverlayError(
                f"미지의 오버레이 키 '{key}' — 허용 형식: 'portfolio.<필드>', "
                "'factor.<팩터id>.<파라미터>', 'rule.<룰id>.threshold'"
            )

    return Overlay(
        portfolio=portfolio, factor_params=factor_params, rule_thresholds=rule_thresholds
    )


def expand_grid(grid: Mapping[str, list[Any]]) -> tuple[dict[str, Any], ...]:
    """`{"a": [1,2], "b": [3]}` -> `({"a":1,"b":3}, {"a":2,"b":3})`.

    키를 정렬해 곱집합을 만들므로 조합 순서가 항상 결정적이다 — 동점 파라미터가 나왔을 때
    폴드마다 다른 값이 뽑히면 안정성 지표 자체가 무의미해진다.
    """
    if not grid:
        return ({},)
    keys = sorted(grid)
    for key in keys:
        if not isinstance(grid[key], (list, tuple)) or not grid[key]:
            raise OverlayError(f"그리드 '{key}'의 값은 비어있지 않은 목록이어야 합니다")
    return tuple(
        dict(zip(keys, combo, strict=True))
        for combo in itertools.product(*(list(grid[key]) for key in keys))
    )


def _merged_params(params: Mapping[str, Any], factor_id: str, overlay: Overlay) -> dict[str, Any]:
    """선택자가 일치하는 대상만 덮어쓴 params. 일치가 없으면 원본과 동일한 사본."""
    merged = dict(params)
    for target, value in overlay.factor_params.items():
        if target.matches(factor_id, params):
            merged[target.param] = value
    return merged


def _touches_factor(factor_id: str, params: Mapping[str, Any], overlay: Overlay) -> bool:
    return any(target.matches(factor_id, params) for target in overlay.factor_params)


def apply_overlay(defn: StrategyDefinition, overlay: Overlay) -> StrategyDefinition:
    """전략 정의에 portfolio·factor_refs·ranking 오버레이를 적용한 파생 정의를 반환한다.

    Rule/Formula 안의 팩터 파라미터와 임계값은 정의가 아니라 리졸버에 있으므로
    `overlay_resolvers`가 담당한다 — 둘을 같이 써야 스윕이 실제로 반영된다.
    """
    if overlay.is_empty:
        return defn

    portfolio = defn.portfolio
    if overlay.portfolio:
        if portfolio is None:
            raise OverlayError(
                f"전략 '{defn.id}'에는 portfolio 정책이 없어 portfolio.* 오버레이를 적용할 수"
                " 없습니다"
            )
        portfolio = dataclasses.replace(portfolio, **dict(overlay.portfolio))

    if portfolio is not None and portfolio.ranking is not None:
        ranking = portfolio.ranking
        if ranking.kind == "factor" and _touches_factor(
            ranking.factor_id, ranking.params, overlay
        ):
            portfolio = dataclasses.replace(
                portfolio,
                ranking=dataclasses.replace(
                    ranking, params=_merged_params(ranking.params, ranking.factor_id, overlay)
                ),
            )

    factor_refs = tuple(
        dataclasses.replace(ref, params=_merged_params(ref.params, ref.factor_id, overlay))
        if _touches_factor(ref.factor_id, ref.params, overlay)
        else ref
        for ref in defn.factor_refs
    )

    return dataclasses.replace(defn, factor_refs=factor_refs, portfolio=portfolio)


def _rewrite_formula_expr(expr: Expr, overlay: Overlay) -> Expr:
    if isinstance(expr, BinaryOp):
        return dataclasses.replace(
            expr,
            left=_rewrite_formula_expr(expr.left, overlay),
            right=_rewrite_formula_expr(expr.right, overlay),
        )
    if isinstance(expr, UnaryOp):
        return dataclasses.replace(expr, operand=_rewrite_formula_expr(expr.operand, overlay))
    if isinstance(expr, FormulaFactorOperand) and _touches_factor(
        expr.factor_id, expr.params, overlay
    ):
        return dataclasses.replace(
            expr, params=_merged_params(expr.params, expr.factor_id, overlay)
        )
    return expr


def _rewrite_rule_node(node: Node, overlay: Overlay) -> Node:
    if isinstance(node, Composition):
        return dataclasses.replace(
            node, operands=tuple(_rewrite_rule_node(child, overlay) for child in node.operands)
        )
    if isinstance(node, Predicate):
        return dataclasses.replace(
            node,
            left=_rewrite_rule_operand(node.left, overlay),
            right=_rewrite_rule_operand(node.right, overlay),
        )
    return node


def _rewrite_rule_operand(operand: Any, overlay: Overlay) -> Any:
    if isinstance(operand, RuleFactorOperand) and _touches_factor(
        operand.factor_id, operand.params, overlay
    ):
        return dataclasses.replace(
            operand, params=_merged_params(operand.params, operand.factor_id, overlay)
        )
    return operand


def _apply_threshold(rule: Rule, value: float) -> Rule:
    """단일 Predicate 룰의 상수 피연산자를 교체한다.

    복잡한 트리(AND/OR 결합, 상수가 여럿)는 "어느 상수인가"가 모호하므로 조용히 첫 번째를
    고르지 않고 **거부한다** — 잘못된 상수를 바꾼 채 통과하면 스윕 결과 전체가 거짓이 된다.
    """
    root = rule.root
    if not isinstance(root, Predicate):
        raise OverlayError(
            f"룰 '{rule.id}'의 루트가 단일 Predicate가 아니라 임계값을 특정할 수 없습니다"
            "(AND/OR로 결합된 룰은 스윕 대상 조건을 별도 룰로 분리하십시오)"
        )
    left_is_const = isinstance(root.left, RuleConstantOperand)
    right_is_const = isinstance(root.right, RuleConstantOperand)
    if left_is_const == right_is_const:
        detail = "상수 피연산자가 없습니다" if not left_is_const else "양쪽이 모두 상수입니다"
        raise OverlayError(f"룰 '{rule.id}'의 임계값을 특정할 수 없습니다({detail})")
    replacement = RuleConstantOperand(value=value)
    if right_is_const:
        return dataclasses.replace(rule, root=dataclasses.replace(root, right=replacement))
    return dataclasses.replace(rule, root=dataclasses.replace(root, left=replacement))


def overlay_resolvers(
    overlay: Overlay,
    resolve_rule: Callable[[str], Rule | None],
    resolve_formula: Callable[[str], Formula | None],
) -> tuple[Callable[[str], Rule | None], Callable[[str], Formula | None]]:
    """평가기에 넘길 리졸버를 오버레이가 적용된 버전으로 감싼다(저장소 무변경).

    미존재 rule_id에 임계값 오버레이를 걸면 조용히 무시되지 않도록 여기서 즉시 실패시킨다 —
    오타 하나로 "스윕은 돌았는데 전부 같은 결과"가 나오는 것을 막는다.
    """
    if overlay.is_empty:
        return resolve_rule, resolve_formula

    def _resolve_rule(rule_id: str) -> Rule | None:
        rule = resolve_rule(rule_id)
        if rule is None:
            return None
        rule = dataclasses.replace(rule, root=_rewrite_rule_node(rule.root, overlay))
        if rule_id in overlay.rule_thresholds:
            rule = _apply_threshold(rule, overlay.rule_thresholds[rule_id])
        return rule

    def _resolve_formula(formula_id: str) -> Formula | None:
        formula = resolve_formula(formula_id)
        if formula is None:
            return None
        return dataclasses.replace(
            formula, expression=_rewrite_formula_expr(formula.expression, overlay)
        )

    for rule_id, value in overlay.rule_thresholds.items():
        rule = resolve_rule(rule_id)
        if rule is None:
            raise OverlayError(f"임계값 오버레이가 미존재 룰 '{rule_id}'을(를) 가리킵니다")
        # 형상 검증만 하고 결과는 버린다 — 실제 적용은 _resolve_rule이 호출 시점에 한다.
        # 여기서 미리 확인하지 않으면 "적용 불가"가 백테스트 실행 중에야 드러나 조합·폴드마다
        # 같은 실패가 반복된 뒤 원인이 파묻힌다.
        _apply_threshold(rule, value)

    return _resolve_rule, _resolve_formula
