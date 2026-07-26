"""screening의 AND/OR/NOT 폴딩이 workspace.rule 평가기와 의미론적으로 동일함을 증명한다.

핵심 아이디어: 양 스키마(rule / screening)에서 각각 Predicate leaf를 만들되, 각 leaf가
가리키는 미리 준비된 boolean pd.Series를 반환하도록 두 평가기의 leaf 비교 함수를 패치한다.
그러면 남는 것은 순전히 Composition 폴딩 로직뿐이며, 동일한 boolean 입력들에 대해 두 폴딩이
항상 동일한 결과를 내는지를 assert_series_equal로 비교할 수 있다.

leaf 트릭: Predicate의 right를 ConstantOperand(value=i)로 두면 broadcast를 거쳐 상수 i가 담긴
Series가 compare()에 전달된다. 패치된 fake_compare는 right.iloc[0]을 인덱스 i로 읽어
사전에 만든 boolean Series 목록의 i번째를 반환한다.
"""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_series_equal

import quant_krx.screening.evaluation as scr_eval
import quant_krx.workspace.numeric as numeric_mod
from quant_krx.factors import FactorInput
from quant_krx.rule.definition import Composition as RuleComposition
from quant_krx.rule.definition import ConstantOperand as RuleConstantOperand
from quant_krx.rule.definition import Predicate as RulePredicate
from quant_krx.screening.definition import Composition as ScrComposition
from quant_krx.screening.definition import ConstantOperand as ScrConstantOperand
from quant_krx.screening.definition import Predicate as ScrPredicate
from quant_krx.screening.evaluation import ScreeningEvaluationContext, _eval_screening_node
from quant_krx.workspace.evaluation import EvaluationContext, _eval_rule_node

_INDEX = pd.date_range("2024-01-01", periods=6, freq="D")

# 다양한 패턴의 boolean Series 6종(폴딩 결과가 자명하지 않도록 서로 다른 비트 패턴).
_BOOL_SERIES = [
    pd.Series([True, False, True, False, True, False], index=_INDEX),
    pd.Series([True, True, False, False, True, True], index=_INDEX),
    pd.Series([False, True, True, True, False, False], index=_INDEX),
    pd.Series([True, True, True, False, False, True], index=_INDEX),
    pd.Series([False, False, False, True, True, True], index=_INDEX),
]


def _fake_compare(op: str, left: pd.Series, right: pd.Series) -> pd.Series:
    """right에 브로드캐스트된 상수를 인덱스로 읽어 사전 준비 boolean Series를 반환한다."""
    idx = int(right.iloc[0])
    return _BOOL_SERIES[idx].copy()


def _build(spec, schema: str):
    """중첩 tuple 스펙을 두 스키마의 노드 트리로 변환한다.

    - int i         → i번째 boolean Series를 가리키는 leaf Predicate
    - (OP, *children) → Composition
    """
    if isinstance(spec, int):
        if schema == "rule":
            return RulePredicate(
                left=RuleConstantOperand(value=0),
                operator=">",
                right=RuleConstantOperand(value=spec),
            )
        return ScrPredicate(
            left=ScrConstantOperand(value=0),
            operator=">",
            right=ScrConstantOperand(value=spec),
        )
    op, *children = spec
    if schema == "rule":
        return RuleComposition(op=op, operands=tuple(_build(c, "rule") for c in children))
    return ScrComposition(op=op, operands=tuple(_build(c, "screening") for c in children))


_SPECS = [
    ("AND", 0, 1, 2),
    ("OR", 0, 1),
    ("NOT", 0),
    ("AND", ("OR", 0, 1), ("NOT", 2), 3),
    ("OR", ("AND", 0, 1, 2), ("NOT", 3), 4),
    ("NOT", ("AND", 0, 1)),
    ("AND", ("OR", ("AND", 0, 1), 2), ("NOT", ("OR", 3, 4))),
]


@pytest.mark.parametrize("spec", _SPECS)
def test_composition_folding_parity(spec, monkeypatch) -> None:
    # rule은 numeric.compare 속성 접근으로 호출하므로 numeric 모듈 속성을 패치.
    monkeypatch.setattr(numeric_mod, "compare", _fake_compare)
    # screening은 import한 이름(compare)을 직접 호출하므로 모듈 바인딩을 패치.
    monkeypatch.setattr(scr_eval, "compare", _fake_compare)

    ohlcv = pd.DataFrame({"close": 1.0}, index=_INDEX)

    rule_ctx = EvaluationContext(
        data=FactorInput(ohlcv=ohlcv), index=_INDEX, resolve_formula=lambda _k: None
    )
    scr_ctx = ScreeningEvaluationContext(ohlcv=ohlcv, index=_INDEX)

    rule_result = _eval_rule_node(_build(spec, "rule"), rule_ctx)
    scr_result = _eval_screening_node(_build(spec, "screening"), scr_ctx)

    assert_series_equal(rule_result, scr_result, check_names=False)
