from __future__ import annotations

from datetime import datetime

import pytest

from quant_krx.formula.definition import ConstantOperand, Formula
from quant_krx.rule.definition import FactorOperand, FormulaOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.service import WorkspaceService

NOW = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture
def svc(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield WorkspaceService(db)
    db.close()


def test_valid_strategy_passes(svc) -> None:
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
    result = svc.validate_strategy(defn)
    assert result.ok


def test_draft_strategy_passes_validation_but_not_runnable(svc) -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    result = svc.validate_strategy(defn)
    assert result.ok


def test_dangling_rule_reference_rejected_with_hint(svc) -> None:
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(),
        rule=RuleBinding(entry=("missing_rule",)),
    )
    result = svc.validate_strategy(defn)
    assert not result.ok
    assert any("missing_rule" in e for e in result.errors)


def test_dangling_formula_reference_after_deletion_rejected(svc) -> None:
    # R02 REQ-P4: 사후 삭제는 계단식 정리하지 않음 — 삭제 후 참조가 dangling이 되는 정상 시나리오.
    formula = Formula(id="tmp_formula", name="tmp", version="1", expression=ConstantOperand(1))
    svc.upsert_formula(formula, now=NOW)
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FormulaOperand("tmp_formula"), ">", FactorOperand("per", "per")),
    )
    svc.upsert_rule(rule, now=NOW)
    svc.delete_formula("tmp_formula")

    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("per"),), universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    result = svc.validate_strategy(defn)
    assert not result.ok
    assert any("tmp_formula" in e for e in result.errors)
