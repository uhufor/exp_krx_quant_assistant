from __future__ import annotations

import dataclasses

import pytest

from quant_krx._jsonnorm import MalformedDefinitionError, SchemaVersionError
from quant_krx.strategy.definition import (
    FactorRef,
    RuleBinding,
    StrategyDefinition,
    Universe,
)


def _draft_definition() -> StrategyDefinition:
    return StrategyDefinition(
        id="my_strategy",
        name="내 전략",
        version="1",
        factor_refs=(FactorRef("sma", {"window": 5}),),
        universe=Universe(),
        rule=None,
    )


def _runnable_definition() -> StrategyDefinition:
    return StrategyDefinition(
        id="my_strategy",
        name="내 전략",
        version="1",
        factor_refs=(FactorRef("sma", {"window": 5}),),
        universe=Universe(symbols=("005930", "000660")),
        rule=RuleBinding(entry=("entry_rule",), exit=("exit_rule",)),
    )


def test_roundtrip_draft() -> None:
    defn = _draft_definition()
    assert StrategyDefinition.from_dict(defn.to_dict()) == defn


def test_roundtrip_runnable_roles() -> None:
    defn = _runnable_definition()
    restored = StrategyDefinition.from_dict(defn.to_dict())
    assert restored == defn
    assert restored.rule.entry == ("entry_rule",)
    assert restored.rule.exit == ("exit_rule",)


def test_frozen_field_assignment_raises() -> None:
    defn = _draft_definition()
    with pytest.raises(dataclasses.FrozenInstanceError):
        defn.name = "변경 시도"  # type: ignore[misc]


def test_future_schema_version_rejected() -> None:
    defn = _draft_definition()
    body = defn.to_dict()
    body["schema_version"] = 999
    with pytest.raises(SchemaVersionError):
        StrategyDefinition.from_dict(body)


def test_universe_rejects_invalid_symbol_format() -> None:
    with pytest.raises(MalformedDefinitionError):
        Universe(symbols=("12345",))  # 5자리
    with pytest.raises(MalformedDefinitionError):
        Universe(symbols=("abcdef",))


def test_universe_empty_tuple_allowed() -> None:
    universe = Universe()
    assert universe.symbols == ()


def test_factor_refs_requires_at_least_one() -> None:
    with pytest.raises(MalformedDefinitionError):
        StrategyDefinition(
            id="s1", name="s1", version="1", factor_refs=(), universe=Universe(), rule=None
        )


def test_rule_binding_whitelist_rejects_inline_body() -> None:
    with pytest.raises(MalformedDefinitionError):
        RuleBinding.from_dict({"node": "predicate", "left": {}, "operator": ">", "right": {}})


def test_rule_binding_whitelist_rejects_rule_ids_shape() -> None:
    with pytest.raises(MalformedDefinitionError):
        RuleBinding.from_dict({"rule_ids": ["r1", "r2"]})


def test_rule_binding_rejects_unknown_role_key() -> None:
    with pytest.raises(MalformedDefinitionError):
        RuleBinding.from_dict({"roles": {"entry": ["r1"], "hold": ["r2"]}})


def test_rule_binding_rejects_empty_entry() -> None:
    with pytest.raises(MalformedDefinitionError):
        RuleBinding(entry=())


def test_rule_binding_allows_missing_exit() -> None:
    binding = RuleBinding(entry=("r1",))
    assert binding.exit == ()
    assert binding.to_dict() == {"roles": {"entry": ["r1"], "exit": []}}


def test_rule_binding_rejects_duplicate_rule_id_within_role() -> None:
    with pytest.raises(MalformedDefinitionError):
        RuleBinding(entry=("r1", "r1"))


def test_rule_binding_preserves_order_roundtrip() -> None:
    binding = RuleBinding(entry=("r2", "r1"), exit=("r4", "r3"))
    restored = RuleBinding.from_dict(binding.to_dict())
    assert restored.entry == ("r2", "r1")
    assert restored.exit == ("r4", "r3")


def test_strategy_rule_none_roundtrips_as_draft() -> None:
    defn = _draft_definition()
    body = defn.to_dict()
    assert body["rule"] is None
    restored = StrategyDefinition.from_dict(body)
    assert restored.rule is None


def test_strategy_schema_has_no_rebalance_field() -> None:
    defn = _runnable_definition()
    assert "rebalance" not in defn.to_dict()
