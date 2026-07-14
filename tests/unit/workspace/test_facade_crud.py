from __future__ import annotations

from datetime import datetime

import pytest

from quant_krx.formula.definition import ConstantOperand, Formula
from quant_krx.rule.definition import FactorOperand, Predicate, Rule
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


def test_formula_crud_roundtrip(svc) -> None:
    formula = Formula(id="m1", name="m1", version="1", expression=ConstantOperand(1))
    svc.upsert_formula(formula, now=NOW)
    assert svc.get_formula("m1") == formula
    assert svc.list_formulas() == (formula,)
    svc.delete_formula("m1")
    assert svc.get_formula("m1") is None


def test_rule_crud_roundtrip(svc) -> None:
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(FactorOperand("sma", "sma"), ">", FactorOperand("per", "per")),
    )
    svc.upsert_rule(rule, now=NOW)
    assert svc.get_rule("r1") == rule
    assert svc.list_rules() == (rule,)
    svc.delete_rule("r1")
    assert svc.get_rule("r1") is None


def test_strategy_crud_roundtrip(svc) -> None:
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
    assert svc.get_strategy("s1") == defn
    assert svc.list_strategies() == (defn,)
    svc.delete_strategy("s1")
    assert svc.get_strategy("s1") is None


def test_list_sorted_by_id(svc) -> None:
    zeta = Formula(id="zeta", name="z", version="1", expression=ConstantOperand(1))
    alpha = Formula(id="alpha", name="a", version="1", expression=ConstantOperand(1))
    svc.upsert_formula(zeta, now=NOW)
    svc.upsert_formula(alpha, now=NOW)
    assert [f.id for f in svc.list_formulas()] == ["alpha", "zeta"]
