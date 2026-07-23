from __future__ import annotations

import pytest

from quant_krx.screening.definition import (
    SCHEMA_VERSION,
    Composition,
    ConstantOperand,
    FactorOperand,
    FormulaOperand,
    Predicate,
    RankPredicate,
    ScanUniverse,
    ScreeningCondition,
    WindowPredicate,
)
from quant_krx.screening.dispatch import node_from_dict
from quant_krx.screening.errors import (
    MalformedDefinitionError,
    SchemaVersionError,
    UnsupportedFilterError,
)


def _sample_predicate() -> Predicate:
    return Predicate(
        left=FactorOperand(factor_id="rsi_14", column="value", params={"period": 14}),
        operator=">",
        right=ConstantOperand(value=70),
    )


def _sample_condition() -> ScreeningCondition:
    window = WindowPredicate(inner=_sample_predicate(), n_bars=5, include_current_bar=True)
    rank = RankPredicate(
        factor_id="momentum_63",
        column="value",
        rank_metric="desc",
        top_n=20,
        params={"lookback": 63},
    )
    formula_pred = Predicate(
        left=FormulaOperand(formula_id="custom_score"),
        operator="crosses_above",
        right=ConstantOperand(value=1.5),
    )
    root = Composition(op="AND", operands=(window, rank, formula_pred))
    return ScreeningCondition(
        id="cond-1",
        name="모멘텀 상위",
        version="1.0.0",
        universe=ScanUniverse(market="KOSPI", exclusion_filters=frozenset({"etf"})),
        root=root,
        metadata={"author": "tester", "tags": ["momentum"]},
    )


# --- 직렬화 왕복 무손실 ---------------------------------------------------


def test_condition_roundtrip_lossless():
    cond = _sample_condition()
    restored = ScreeningCondition.from_dict(cond.to_dict())
    assert restored == cond
    assert restored.to_dict() == cond.to_dict()


def test_node_dispatch_roundtrip_all_node_types():
    nodes = [
        _sample_predicate(),
        WindowPredicate(inner=_sample_predicate(), n_bars=0, include_current_bar=False),
        RankPredicate(factor_id="f", column="value", rank_metric="asc", top_n=1),
        Composition(op="NOT", operands=(_sample_predicate(),)),
    ]
    for node in nodes:
        assert node_from_dict(node.to_dict()) == node


def test_scan_universe_roundtrip():
    uni = ScanUniverse(market="KOSDAQ", exclusion_filters=frozenset({"spac", "reit"}))
    assert ScanUniverse.from_dict(uni.to_dict()) == uni


# --- n_bars / top_n 잘못된 값 거부 ---------------------------------------


@pytest.mark.parametrize("bad", [-1, -10, True, 1.5, "5"])
def test_window_predicate_rejects_bad_n_bars(bad):
    with pytest.raises(MalformedDefinitionError):
        WindowPredicate(inner=_sample_predicate(), n_bars=bad, include_current_bar=True)


def test_window_predicate_accepts_zero_n_bars():
    wp = WindowPredicate(inner=_sample_predicate(), n_bars=0, include_current_bar=True)
    assert wp.n_bars == 0


@pytest.mark.parametrize("bad", [0, -1, True, 2.0, "3"])
def test_rank_predicate_rejects_bad_top_n(bad):
    with pytest.raises(MalformedDefinitionError):
        RankPredicate(factor_id="f", column="value", rank_metric="desc", top_n=bad)


def test_rank_predicate_rejects_bad_metric():
    with pytest.raises(MalformedDefinitionError):
        RankPredicate(factor_id="f", column="value", rank_metric="ascending", top_n=5)


# --- constant operand 경계 ------------------------------------------------


@pytest.mark.parametrize("bad", [True, False, float("nan"), float("inf"), float("-inf")])
def test_constant_operand_rejects_bad_values(bad):
    with pytest.raises(MalformedDefinitionError):
        ConstantOperand(value=bad)


# --- schema_version 다운그레이드 차단 -------------------------------------


def test_schema_version_downgrade_blocked():
    payload = _sample_condition().to_dict()
    payload["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(SchemaVersionError):
        ScreeningCondition.from_dict(payload)


def test_schema_version_current_ok():
    payload = _sample_condition().to_dict()
    assert ScreeningCondition.from_dict(payload).schema_version == SCHEMA_VERSION


# --- 미지원 제외 필터 거부 ------------------------------------------------


@pytest.mark.parametrize(
    "flt",
    [
        "administrative_issue",
        "investment_alert",
        "trading_halt",
        "liquidation_trading",
        "market_alert",
        "unfaithful_disclosure",
    ],
)
def test_scan_universe_rejects_unsupported_filter(flt):
    with pytest.raises(UnsupportedFilterError) as exc:
        ScanUniverse(exclusion_filters=frozenset({flt}))
    assert flt in str(exc.value)


def test_scan_universe_allows_supported_filters():
    uni = ScanUniverse(exclusion_filters=frozenset({"etf", "spac"}))
    assert uni.exclusion_filters == frozenset({"etf", "spac"})


# --- 디스패치 오류 --------------------------------------------------------


def test_node_from_dict_unknown_tag():
    with pytest.raises(MalformedDefinitionError):
        node_from_dict({"node": "unknown_tag"})


def test_node_from_dict_missing_tag():
    with pytest.raises(MalformedDefinitionError):
        node_from_dict({})


def test_composition_arity_enforced():
    with pytest.raises(MalformedDefinitionError):
        Composition(op="AND", operands=(_sample_predicate(),))
    with pytest.raises(MalformedDefinitionError):
        Composition(op="NOT", operands=(_sample_predicate(), _sample_predicate()))
