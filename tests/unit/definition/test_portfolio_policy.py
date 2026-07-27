from __future__ import annotations

import pytest

from quant_krx.strategy.definition import (
    FactorRef,
    PortfolioPolicy,
    RankingSpec,
    RuleBinding,
    StrategyDefinition,
    Universe,
)
from quant_krx.strategy.errors import MalformedDefinitionError
from quant_krx.strategy.validation import validate_definition


def _defn(**kwargs) -> StrategyDefinition:
    base = dict(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}),),
        universe=Universe(),
        rule=RuleBinding(entry=("r1",)),
    )
    base.update(kwargs)
    return StrategyDefinition(**base)


# --- 왕복 무손실(불변식 3) ---


def test_strategy_without_portfolio_roundtrips():
    defn = _defn()
    assert StrategyDefinition.from_dict(defn.to_dict()) == defn
    assert defn.to_dict()["portfolio"] is None


def test_strategy_with_portfolio_roundtrips():
    defn = _defn(portfolio=PortfolioPolicy(max_positions=3, rebalance="quarterly"))
    assert StrategyDefinition.from_dict(defn.to_dict()) == defn


def test_portfolio_with_factor_ranking_roundtrips():
    policy = PortfolioPolicy(
        max_positions=5,
        ranking=RankingSpec(kind="factor", factor_id="rsi", column="rsi", params={"window": 14}),
    )
    defn = _defn(portfolio=policy)
    assert StrategyDefinition.from_dict(defn.to_dict()) == defn


def test_portfolio_with_formula_ranking_roundtrips():
    policy = PortfolioPolicy(
        max_positions=2, ranking=RankingSpec(kind="formula", formula_id="my_score")
    )
    defn = _defn(portfolio=policy)
    assert StrategyDefinition.from_dict(defn.to_dict()) == defn


def test_legacy_schema_version_1_still_loads():
    """portfolio 이전(v1)에 저장된 정의도 그대로 읽혀야 한다(additive 진화)."""
    raw = _defn().to_dict()
    raw["schema_version"] = 1
    raw.pop("portfolio")
    loaded = StrategyDefinition.from_dict(raw)
    assert loaded.portfolio is None
    assert loaded.schema_version == 1


# --- fail-closed 검증 ---


@pytest.mark.parametrize("bad", [0, -1])
def test_max_positions_must_be_positive(bad):
    with pytest.raises(MalformedDefinitionError, match="max_positions"):
        PortfolioPolicy(max_positions=bad)


def test_unknown_rebalance_rejected():
    with pytest.raises(MalformedDefinitionError, match="rebalance"):
        PortfolioPolicy(max_positions=2, rebalance="daily")


def test_unknown_sizing_rejected():
    with pytest.raises(MalformedDefinitionError, match="sizing"):
        PortfolioPolicy(max_positions=2, sizing="inverse_volatility")


def test_non_positive_initial_cash_rejected():
    with pytest.raises(MalformedDefinitionError, match="initial_cash"):
        PortfolioPolicy(max_positions=2, initial_cash=0)


def test_unknown_portfolio_field_rejected():
    """선언되지 않은 필드를 조용히 무시하지 않는다(선언-실행 괴리 차단)."""
    with pytest.raises(MalformedDefinitionError, match="미지의 portfolio 필드"):
        PortfolioPolicy.from_dict({"max_positions": 2, "stop_loss": 0.1})


def test_ranking_factor_requires_factor_id_and_column():
    with pytest.raises(MalformedDefinitionError, match="factor_id와 column"):
        RankingSpec(kind="factor", factor_id="sma")


def test_ranking_formula_requires_formula_id():
    with pytest.raises(MalformedDefinitionError, match="formula_id가 필요"):
        RankingSpec(kind="formula")


def test_ranking_kind_mixing_rejected():
    with pytest.raises(MalformedDefinitionError, match="formula_id를 지정할 수 없습니다"):
        RankingSpec(kind="factor", factor_id="sma", column="sma", formula_id="x")


def test_unknown_ranking_kind_rejected():
    with pytest.raises(MalformedDefinitionError, match="미지의 ranking.kind"):
        RankingSpec(kind="momentum")


# --- 저장 시점 참조 무결성(불변식 4) ---


def test_validate_rejects_unknown_ranking_factor():
    defn = _defn(
        portfolio=PortfolioPolicy(
            max_positions=2, ranking=RankingSpec(kind="factor", factor_id="no_such", column="x")
        )
    )
    result = validate_definition(defn)
    assert not result.ok
    assert any("미존재 factor_id 'no_such'" in e for e in result.errors)


def test_validate_rejects_unknown_ranking_column():
    defn = _defn(
        portfolio=PortfolioPolicy(
            max_positions=2,
            ranking=RankingSpec(kind="factor", factor_id="sma", column="no_such_column"),
        )
    )
    result = validate_definition(defn)
    assert not result.ok
    assert any("no_such_column" in e for e in result.errors)


def test_validate_rejects_bad_ranking_params():
    defn = _defn(
        portfolio=PortfolioPolicy(
            max_positions=2,
            ranking=RankingSpec(
                kind="factor", factor_id="sma", column="sma", params={"window": -5}
            ),
        )
    )
    result = validate_definition(defn)
    assert not result.ok
    assert any("portfolio.ranking" in e for e in result.errors)


def test_validate_rejects_missing_ranking_formula():
    defn = _defn(
        portfolio=PortfolioPolicy(
            max_positions=2, ranking=RankingSpec(kind="formula", formula_id="ghost")
        )
    )

    class _Rule:
        root = None

    result = validate_definition(
        defn, resolve_rule=lambda _: _Rule(), resolve_formula=lambda _: None
    )
    assert not result.ok
    assert any("ghost" in e for e in result.errors)


def test_ranking_factor_counts_toward_factor_refs():
    """ranking 팩터도 factor_refs에 선언되어야 하고, 선언하면 '잉여'로 거부되지 않는다."""
    from quant_krx.rule.definition import ConstantOperand, FactorOperand, Predicate, Rule

    rule = Rule(
        id="r1", name="r", version="1",
        root=Predicate(FactorOperand("sma", "sma", {"window": 5}), ">", ConstantOperand(0.0)),
    )
    policy = PortfolioPolicy(
        max_positions=2, ranking=RankingSpec(kind="factor", factor_id="rsi", column="rsi")
    )

    # rule은 sma만, ranking은 rsi를 쓰므로 factor_refs에는 둘 다 있어야 한다.
    both = _defn(
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("rsi")), portfolio=policy
    )
    assert validate_definition(both, resolve_rule=lambda _: rule, resolve_formula=lambda _: None).ok

    # ranking 팩터를 빠뜨리면 누락으로 잡혀야 한다.
    missing = _defn(factor_refs=(FactorRef("sma", {"window": 5}),), portfolio=policy)
    result = validate_definition(
        missing, resolve_rule=lambda _: rule, resolve_formula=lambda _: None
    )
    assert not result.ok
    assert any("rsi" in e for e in result.errors)
