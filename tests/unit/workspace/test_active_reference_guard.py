from __future__ import annotations

from datetime import datetime

import pytest

from quant_krx.formula.definition import ConstantOperand, Formula
from quant_krx.formula.definition import FormulaOperand as FormulaFormulaOperand
from quant_krx.rule.definition import FactorOperand, FormulaOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.errors import WorkspaceError
from quant_krx.workspace.service import WorkspaceService

NOW = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture
def svc(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield WorkspaceService(db)
    db.close()


def _activate_strategy_referencing_rule(svc: WorkspaceService) -> None:
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


def test_active_strategy_self_upsert_blocked(svc) -> None:
    _activate_strategy_referencing_rule(svc)
    defn = svc.get_strategy("s1")
    with pytest.raises(WorkspaceError, match="s1"):
        svc.upsert_strategy(defn, now=NOW)


def test_active_strategy_self_delete_blocked(svc) -> None:
    _activate_strategy_referencing_rule(svc)
    with pytest.raises(WorkspaceError, match="s1"):
        svc.delete_strategy("s1")


def test_active_strategy_referenced_rule_upsert_blocked(svc) -> None:
    _activate_strategy_referencing_rule(svc)
    rule = svc.get_rule("entry_rule")
    with pytest.raises(WorkspaceError, match="s1"):
        svc.upsert_rule(rule, now=NOW)


def test_active_strategy_referenced_rule_delete_blocked(svc) -> None:
    _activate_strategy_referencing_rule(svc)
    with pytest.raises(WorkspaceError, match="s1"):
        svc.delete_rule("entry_rule")


def test_active_strategy_transitively_referenced_formula_blocked(svc) -> None:
    base_formula = Formula(
        id="base_metric", name="base", version="1", expression=ConstantOperand(1)
    )
    svc.upsert_formula(base_formula, now=NOW)
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FormulaOperand("base_metric"), ">", FactorOperand("per", "per")),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("per"),), universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    svc.activate("s1", now=NOW)

    with pytest.raises(WorkspaceError, match="s1"):
        svc.upsert_formula(base_formula, now=NOW)
    with pytest.raises(WorkspaceError, match="s1"):
        svc.delete_formula("base_metric")


def test_deactivate_then_allows_modification(svc) -> None:
    _activate_strategy_referencing_rule(svc)
    svc.deactivate("s1", now=NOW)
    rule = svc.get_rule("entry_rule")
    svc.upsert_rule(rule, now=NOW)  # 더 이상 차단되지 않음
    svc.delete_rule("entry_rule")


def test_unrelated_formula_not_blocked(svc) -> None:
    _activate_strategy_referencing_rule(svc)
    unrelated = Formula(id="unrelated", name="u", version="1", expression=ConstantOperand(1))
    svc.upsert_formula(unrelated, now=NOW)
    svc.delete_formula("unrelated")


def test_formula_operand_ids_helper_ignores_non_formula_leaves() -> None:
    # 회귀 방지용 — FactorOperand/ConstantOperand는 formula_id를 갖지 않으므로 무시되어야 함
    from quant_krx.workspace.service import _formula_operand_ids

    assert _formula_operand_ids(ConstantOperand(1)) == []
    assert _formula_operand_ids(FormulaFormulaOperand("x")) == ["x"]
