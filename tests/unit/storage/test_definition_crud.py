from __future__ import annotations

from datetime import datetime

import pytest

from quant_krx._jsonnorm import DefinitionValidationError
from quant_krx.formula.definition import ConstantOperand, FactorOperand, Formula, FormulaOperand
from quant_krx.rule.definition import FactorOperand as RuleFactorOperand
from quant_krx.rule.definition import Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield db
    db.close()


NOW = datetime(2026, 1, 1, 0, 0, 0)
LATER = datetime(2026, 1, 2, 0, 0, 0)


def test_definition_tables_exist_and_reconnect_idempotent(tmp_db, tmp_path):
    db2 = Database(path=tmp_path / "test.duckdb")
    db2.connect()
    with db2.cursor() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
    assert {"formulas", "rules", "strategies"} <= tables
    db2.close()


def test_formula_crud_roundtrip(tmp_db):
    formula = Formula(id="m1", name="m1", version="1", expression=ConstantOperand(1))
    tmp_db.upsert_formula(formula, now=NOW)
    assert tmp_db.get_formula("m1") == formula
    assert tmp_db.list_formulas() == (formula,)
    tmp_db.delete_formula("m1")
    assert tmp_db.get_formula("m1") is None


def test_formula_upsert_idempotent_preserves_created_at(tmp_db):
    formula = Formula(id="m1", name="m1", version="1", expression=ConstantOperand(1))
    tmp_db.upsert_formula(formula, now=NOW)
    formula_v2 = Formula(id="m1", name="m1 갱신", version="2", expression=ConstantOperand(2))
    tmp_db.upsert_formula(formula_v2, now=LATER)

    with tmp_db.cursor() as conn:
        row = conn.execute(
            "SELECT created_at, updated_at FROM formulas WHERE id=?", ["m1"]
        ).fetchone()
    assert row[0] == NOW
    assert row[1] == LATER
    assert len(tmp_db.list_formulas()) == 1
    assert tmp_db.get_formula("m1") == formula_v2


def test_list_formulas_sorted_by_id(tmp_db):
    zeta = Formula(id="zeta", name="z", version="1", expression=ConstantOperand(1))
    alpha = Formula(id="alpha", name="a", version="1", expression=ConstantOperand(1))
    tmp_db.upsert_formula(zeta, now=NOW)
    tmp_db.upsert_formula(alpha, now=NOW)
    ids = [f.id for f in tmp_db.list_formulas()]
    assert ids == ["alpha", "zeta"]


def test_upsert_formula_invalid_definition_rejected_and_store_unchanged(tmp_db):
    invalid = Formula(
        id="m1", name="m1", version="1", expression=FactorOperand("no_such_factor", "x")
    )
    with pytest.raises(DefinitionValidationError):
        tmp_db.upsert_formula(invalid, now=NOW)
    assert tmp_db.list_formulas() == ()


def test_upsert_formula_cyclic_rejected_and_store_unchanged(tmp_db):
    base = Formula(id="f1", name="f1", version="1", expression=FormulaOperand("f2"))
    tmp_db.upsert_formula(base, now=NOW, check_formula_store=False)  # 부분 조립(완화)

    cyclic = Formula(id="f2", name="f2", version="1", expression=FormulaOperand("f1"))
    with pytest.raises(DefinitionValidationError):
        tmp_db.upsert_formula(cyclic, now=NOW)
    assert tmp_db.get_formula("f2") is None
    assert len(tmp_db.list_formulas()) == 1


def test_upsert_formula_self_reference_reports_cycle_hint_not_missing_ref(tmp_db):
    # 자기참조 시 upsert 대상이 아직 store에 없더라도 "미존재"가 아니라 순환 힌트가
    # 우선 보고되어야 한다(진단 품질, strict는 첫 오류만 raise).
    self_ref = Formula(id="sr", name="sr", version="1", expression=FormulaOperand("sr"))
    with pytest.raises(DefinitionValidationError, match="순환"):
        tmp_db.upsert_formula(self_ref, now=NOW)
    assert tmp_db.get_formula("sr") is None


def test_rule_crud_roundtrip(tmp_db):
    rule = Rule(
        id="r1", name="r1", version="1",
        root=Predicate(RuleFactorOperand("sma", "sma"), ">", RuleFactorOperand("per", "per")),
    )
    tmp_db.upsert_rule(rule, now=NOW)
    assert tmp_db.get_rule("r1") == rule
    assert tmp_db.list_rules() == (rule,)
    tmp_db.delete_rule("r1")
    assert tmp_db.get_rule("r1") is None


def test_strategy_crud_roundtrip(tmp_db):
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(RuleFactorOperand("sma", "sma"), ">", RuleFactorOperand("per", "per")),
    )
    tmp_db.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"), FactorRef("per")),
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    tmp_db.upsert_strategy(defn, now=NOW)
    assert tmp_db.get_strategy("s1") == defn
    assert tmp_db.list_strategies() == (defn,)
    tmp_db.delete_strategy("s1")
    assert tmp_db.get_strategy("s1") is None


def test_upsert_strategy_invalid_definition_rejected_and_store_unchanged(tmp_db):
    defn = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(),
        rule=RuleBinding(entry=("missing_rule",)),
    )
    with pytest.raises(DefinitionValidationError):
        tmp_db.upsert_strategy(defn, now=NOW)
    assert tmp_db.list_strategies() == ()


def test_shared_reference_across_multiple_entities(tmp_db):
    base_formula = Formula(id="base", name="base", version="1", expression=ConstantOperand(1))
    tmp_db.upsert_formula(base_formula, now=NOW)

    rule_a = Rule(
        id="rule_a", name="a", version="1",
        root=Predicate(RuleFactorOperand("sma", "sma"), ">", RuleFactorOperand("per", "per")),
    )
    rule_b = Rule(
        id="rule_b", name="b", version="1",
        root=Predicate(RuleFactorOperand("rsi", "rsi"), "<", RuleFactorOperand("per", "per")),
    )
    tmp_db.upsert_rule(rule_a, now=NOW)
    tmp_db.upsert_rule(rule_b, now=NOW)

    strategy1 = StrategyDefinition(
        id="strat1", name="s1", version="1",
        factor_refs=(FactorRef("sma"), FactorRef("per")), universe=Universe(),
        rule=RuleBinding(entry=("rule_a",)),
    )
    strategy2 = StrategyDefinition(
        id="strat2", name="s2", version="1",
        factor_refs=(FactorRef("rsi"), FactorRef("per")), universe=Universe(),
        rule=RuleBinding(entry=("rule_b",)),
    )
    tmp_db.upsert_strategy(strategy1, now=NOW)
    tmp_db.upsert_strategy(strategy2, now=NOW)

    assert len(tmp_db.list_strategies()) == 2
    assert len(tmp_db.list_rules()) == 2


def test_check_formula_store_flag_disabled_skips_reference_validation(tmp_db):
    dangling = Formula(id="m1", name="m1", version="1", expression=FormulaOperand("does_not_exist"))
    tmp_db.upsert_formula(dangling, now=NOW, check_formula_store=False)
    assert tmp_db.get_formula("m1") == dangling
