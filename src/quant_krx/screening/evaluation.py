from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quant_krx._jsonnorm import canonical_json
from quant_krx.factors import compute_factor, get_factor, get_factor_notes
from quant_krx.screening.definition import (
    Composition,
    ConstantOperand,
    FactorOperand,
    FormulaOperand,
    Node,
    Operand,
    Predicate,
    RankPredicate,
    WindowPredicate,
)
from quant_krx.screening.errors import ScreeningError

# leaf(비교/교차) 로직은 rule 평가기와 완전히 동일한 코드를 써야 드리프트가 구조적으로
# 불가능해진다(3라운드 컨센서스 결론) — 따라서 workspace.numeric의 compare/crosses/broadcast를
# 재구현하지 않고 그대로 import해서 호출한다. workspace.numeric은 순수 유틸이며
# workspace.evaluation(격리 금지 대상)과 무관하므로 INV-2 격리를 위반하지 않는다.
from quant_krx.workspace.numeric import broadcast, compare, crosses

_CROSS_OPERATORS = frozenset({"crosses_above", "crosses_below"})

FactorLookbackResolver = Callable[[str, dict[str, Any]], int]

# 기본 lookback resolver 설정 — 다음 스토리에서 팩터별 정밀 계산으로 대체될 임시 휴리스틱.
_LOOKBACK_PARAM_NAMES = frozenset({"window", "slow", "lookback", "span", "period"})
_LOOKBACK_MARGIN = 5
_DEFAULT_LOOKBACK = 60


@dataclass
class ScreeningEvaluationContext:
    """단일 종목 스크리닝 평가 컨텍스트 — 팩터 계산 캐시 소유.

    workspace.evaluation.EvaluationContext와 동일 패턴이나 독립 구현(격리, INV-2)이며,
    screening은 FactorInput/펀더멘털을 다루지 않고 순수 OHLCV DataFrame만 취급한다.
    ohlcv는 동적 lookback으로 이미 잘라낸 구간이고, index는 그 기준 인덱스다.
    """

    ohlcv: pd.DataFrame
    index: pd.DatetimeIndex
    rank_membership: Mapping[RankPredicate, set[str]] | None = None
    current_symbol: str | None = None
    _factor_cache: dict[tuple[str, str, str], pd.Series] = field(default_factory=dict)


def _eval_factor_operand(
    factor_id: str, column: str, params: dict[str, Any], ctx: ScreeningEvaluationContext
) -> pd.Series:
    """캐시 키 (factor_id, column, canonical(params)) — 상이 파라미터/컬럼은 별개 시계열."""
    key = (factor_id, column, canonical_json(params))
    cached = ctx._factor_cache.get(key)
    if cached is not None:
        return cached
    factor = get_factor(factor_id, **params)
    result_df = compute_factor(factor, ctx.ohlcv)
    get_factor_notes(result_df)  # 반환 직후 판독(R01 advisory 계약 준수)
    series = result_df[column].reindex(ctx.index)
    ctx._factor_cache[key] = series
    return series


def _eval_operand(operand: Operand, ctx: ScreeningEvaluationContext) -> pd.Series:
    if isinstance(operand, FactorOperand):
        return _eval_factor_operand(operand.factor_id, operand.column, dict(operand.params), ctx)
    if isinstance(operand, ConstantOperand):
        return broadcast(float(operand.value), ctx.index)
    if isinstance(operand, FormulaOperand):
        raise ScreeningError(
            "FormulaOperand는 screening leaf 평가에서 아직 지원되지 않습니다"
            f"(formula_id={operand.formula_id!r}) — screening은 formula 패키지를 참조하지"
            " 않는 격리 계층이므로 별도 스토리에서 다룬다"
        )
    raise ScreeningError(f"미지의 screening 피연산자입니다: {operand!r}")


def _apply_window(series: pd.Series, n_bars: int, include_current_bar: bool) -> pd.Series:
    """최근 n_bars봉 중 하나라도 True면 현재 봉도 True로 판정한다.

    include_current_bar=True  → 현재봉 포함 과거 n_bars개(window=n_bars+1).
    include_current_bar=False → 현재봉 제외 과거 n_bars개(shift(1) 후 rolling(n_bars)).

    경계: (n_bars=0, include=True)은 원본과 동일, (n_bars=0, include=False)은 전부 False.
    """
    numeric = series.astype("float64")
    if include_current_bar:
        rolled = numeric.rolling(window=n_bars + 1, min_periods=1).max()
        return rolled.astype(bool)
    if n_bars == 0:
        return pd.Series(False, index=series.index, dtype=bool)
    rolled = numeric.shift(1).rolling(window=n_bars, min_periods=1).max()
    return rolled.fillna(False).astype(bool)


def _eval_screening_node(node: Node, ctx: ScreeningEvaluationContext) -> pd.Series:
    """screening 조건 트리를 순회 평가한다 → pd.Series(dtype=bool, 기준 인덱스 정렬)."""
    if isinstance(node, Predicate):
        left = _eval_operand(node.left, ctx)
        right = _eval_operand(node.right, ctx)
        if node.operator in _CROSS_OPERATORS:
            return crosses(node.operator, left, right)
        return compare(node.operator, left, right)
    if isinstance(node, Composition):
        # workspace.evaluation._eval_rule_node의 AND/OR/NOT 폴딩과 동일 의미론의 독립 재구현
        # (workspace.evaluation을 import하지 않음, 격리 원칙).
        children = [_eval_screening_node(child, ctx) for child in node.operands]
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
    if isinstance(node, WindowPredicate):
        inner = _eval_screening_node(node.inner, ctx)
        return _apply_window(inner, node.n_bars, node.include_current_bar)
    if isinstance(node, RankPredicate):
        # RankPredicate는 시계열이 아니라 as_of 시점의 정적 횡단면 사실이므로, universe 단위로
        # 미리 계산한 통과 집합(ctx.rank_membership)에서 현재 종목 소속 여부를 조회해 전체 True 또는
        # 전체 False인 상수 Series로 반환한다. rank_membership이 None이면(사전 계산 미제공)
        # 기존처럼 거부해 하위 호환을 유지한다.
        if ctx.rank_membership is None:
            raise ScreeningError(
                "RankPredicate는 universe 단위 평가 전용 — 조건 트리에서 미리 추출해 ranking.py로"
                " 위임해야 함(ScreeningEvaluationContext.rank_membership 미제공)"
            )
        if node not in ctx.rank_membership:
            raise ScreeningError(
                "RankPredicate 사전 계산 결과가 rank_membership에 없습니다"
                f"(factor_id={node.factor_id!r}, column={node.column!r}) — apply_rank_predicates를"
                " 동일 조건 트리로 먼저 호출해야 합니다"
            )
        passed = ctx.current_symbol in ctx.rank_membership[node]
        return pd.Series(passed, index=ctx.index, dtype=bool)
    raise ScreeningError(f"미지의 screening 노드입니다: {node!r}")


def extract_rank_predicates(node: Node) -> list[RankPredicate]:
    """조건 트리를 순회해 모든 RankPredicate 리프를 수집한다(순위 엔진 스토리에서 사용)."""
    if isinstance(node, RankPredicate):
        return [node]
    if isinstance(node, Composition):
        collected: list[RankPredicate] = []
        for child in node.operands:
            collected.extend(extract_rank_predicates(child))
        return collected
    if isinstance(node, WindowPredicate):
        return extract_rank_predicates(node.inner)
    return []


def tree_requires_ohlcv(node: Node) -> bool:
    """조건 트리가 종목별 시계열 OHLCV 평가를 필요로 하는지 여부.

    RankPredicate는 as_of 시점 시장 스냅샷만으로 평가되는 정적 횡단면 사실이라
    OHLCV 이력이 전혀 필요 없다(evaluation.py의 RankPredicate 분기 참고). 트리 전체가
    RankPredicate로만 구성되면(예: "거래대금 Top100 AND 거래량 Top100") OHLCV 확보 자체를
    생략할 수 있다 — 결측/일시 조회 실패 종목이 순수 순위 조건에서 부당하게 탈락하는 것을
    막고(정확성), 불필요한 대량 OHLCV fetch도 피한다(성능). WindowPredicate는 inner가
    실제로 OHLCV를 요구할 때만 필요하다고 판단한다(내부가 RankPredicate뿐이면 결과가
    항상 상수이므로 windowing이 무의미하되 안전하다).
    """
    if isinstance(node, RankPredicate):
        return False
    if isinstance(node, Predicate):
        return True
    if isinstance(node, Composition):
        return any(tree_requires_ohlcv(child) for child in node.operands)
    if isinstance(node, WindowPredicate):
        return tree_requires_ohlcv(node.inner)
    return True


def default_factor_lookback_resolver(factor_id: str, params: Mapping[str, Any]) -> int:
    """팩터별 warm-up 봉수 기본 추정 — 흔한 파라미터명에서 값을 찾아 여유를 더한다.

    완벽할 필요 없는 임시 휴리스틱(다음 스토리에서 정밀화). window/slow/lookback/span/period
    중 발견한 최댓값 + 여유(_LOOKBACK_MARGIN)를 반환하고, 하나도 없으면 안전한 기본값을 쓴다.
    """
    candidates = [
        value
        for name, value in params.items()
        if name in _LOOKBACK_PARAM_NAMES
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ]
    if not candidates:
        return _DEFAULT_LOOKBACK
    return int(max(candidates)) + _LOOKBACK_MARGIN


def estimate_required_lookback(
    node: Node, *, factor_lookback_resolver: FactorLookbackResolver
) -> int:
    """조건 트리가 요구하는 최대 이력 봉수를 산정한다.

    WindowPredicate는 n_bars만큼의 추가 이력이 내부 노드 요구량 위에 필요하므로 합산하고,
    형제/자식 분기 사이에서는 최댓값을 취한다.
    """
    if isinstance(node, Predicate):
        needs = [0]
        for operand in (node.left, node.right):
            if isinstance(operand, FactorOperand):
                needs.append(factor_lookback_resolver(operand.factor_id, dict(operand.params)))
        return max(needs)
    if isinstance(node, Composition):
        return max(
            (
                estimate_required_lookback(child, factor_lookback_resolver=factor_lookback_resolver)
                for child in node.operands
            ),
            default=0,
        )
    if isinstance(node, WindowPredicate):
        inner = estimate_required_lookback(
            node.inner, factor_lookback_resolver=factor_lookback_resolver
        )
        return node.n_bars + inner
    if isinstance(node, RankPredicate):
        # RankPredicate는 시장 스냅샷(as_of 단일 시점)만으로 평가되고 종목별 시계열을
        # 전혀 쓰지 않으므로(tree_requires_ohlcv 참고) 이력이 필요 없다(0봉).
        return 0
    return 0
