from __future__ import annotations

from datetime import datetime

import pytest

from quant_krx.rule.definition import FactorOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.errors import WorkspaceError
from quant_krx.workspace.service import WorkspaceService

NOW = datetime(2026, 1, 1, 0, 0, 0)
LATER = datetime(2026, 1, 2, 0, 0, 0)


@pytest.fixture
def svc(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield WorkspaceService(db)
    db.close()


def _seed_runnable_strategy(svc: WorkspaceService, strategy_id: str) -> None:
    rule_id = f"{strategy_id}_rule"
    rule = Rule(
        id=rule_id, name=rule_id, version="1",
        root=Predicate(FactorOperand("sma", "sma"), ">", FactorOperand("per", "per")),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id=strategy_id, name=strategy_id, version="1",
        factor_refs=(FactorRef("sma"), FactorRef("per")),
        universe=Universe(),
        rule=RuleBinding(entry=(rule_id,)),
    )
    svc.upsert_strategy(defn, now=NOW)


def test_is_active_missing_row_is_false(svc) -> None:
    assert svc.is_active("no_such_strategy") is False


def test_activate_deactivate_idempotent(svc) -> None:
    _seed_runnable_strategy(svc, "s1")

    svc.activate("s1", now=NOW)
    assert svc.is_active("s1") is True
    svc.activate("s1", now=LATER)
    assert svc.is_active("s1") is True
    assert svc.list_active() == ("s1",)

    svc.deactivate("s1", now=NOW)
    assert svc.is_active("s1") is False
    svc.deactivate("s1", now=LATER)
    assert svc.is_active("s1") is False
    assert svc.list_active() == ()


def test_list_active_sorted_by_id(svc) -> None:
    _seed_runnable_strategy(svc, "zeta")
    _seed_runnable_strategy(svc, "alpha")
    svc.activate("zeta", now=NOW)
    svc.activate("alpha", now=NOW)
    assert svc.list_active() == ("alpha", "zeta")


def test_activate_missing_strategy_rejected(svc) -> None:
    with pytest.raises(WorkspaceError):
        svc.activate("no_such_strategy", now=NOW)


def test_activate_draft_strategy_rejected(svc) -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    svc.upsert_strategy(defn, now=NOW)
    with pytest.raises(WorkspaceError):
        svc.activate("s1", now=NOW)
    assert svc.is_active("s1") is False


def test_activate_validation_failure_rejected(svc) -> None:
    # 저장 시점엔 유효했으나 사후 삭제(R02 REQ-P4, 비계단식)로 dangling이 된 시나리오.
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FactorOperand("sma", "sma"), ">", FactorOperand("per", "per")),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"), FactorRef("per")),
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    svc.delete_rule("entry_rule")

    with pytest.raises(WorkspaceError):
        svc.activate("s1", now=NOW)
    assert svc.is_active("s1") is False


def test_activate_valid_runnable_strategy_succeeds(svc) -> None:
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FactorOperand("sma", "sma"), ">", FactorOperand("per", "per")),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"), FactorRef("per")),
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    svc.activate("s1", now=NOW)
    assert svc.is_active("s1") is True
