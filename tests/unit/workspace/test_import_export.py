from __future__ import annotations

from datetime import datetime

import pytest

from quant_krx._jsonnorm import DefinitionValidationError, canonical_json
from quant_krx.formula.definition import ConstantOperand, Formula
from quant_krx.rule.definition import FactorOperand, FormulaOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.errors import WorkspaceError
from quant_krx.workspace.service import WorkspaceService
from quant_krx.workspace.templates import StrategyBundle

NOW = datetime(2026, 1, 1, 0, 0, 0)
LATER = datetime(2026, 1, 2, 0, 0, 0)


@pytest.fixture
def svc(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield WorkspaceService(db)
    db.close()


def _build_strategy_with_formula(svc: WorkspaceService, strategy_id: str) -> StrategyDefinition:
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
        id=strategy_id, name=strategy_id, version="1",
        factor_refs=(FactorRef("per"),), universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    return defn


def test_export_includes_transitive_formula_closure(svc) -> None:
    _build_strategy_with_formula(svc, "s1")
    bundle = svc.export_strategy("s1")
    assert bundle.strategy.id == "s1"
    assert {r.id for r in bundle.rules} == {"entry_rule"}
    assert {f.id for f in bundle.formulas} == {"base_metric"}


def test_export_two_calls_byte_identical(svc) -> None:
    _build_strategy_with_formula(svc, "s1")
    bundle1 = svc.export_strategy("s1")
    bundle2 = svc.export_strategy("s1")
    assert canonical_json(bundle1.to_dict()) == canonical_json(bundle2.to_dict())


def test_export_missing_strategy_rejected(svc) -> None:
    with pytest.raises(WorkspaceError):
        svc.export_strategy("no_such")


def test_export_then_import_roundtrip_restores_equal_definition(svc, tmp_path) -> None:
    _build_strategy_with_formula(svc, "s1")
    bundle = svc.export_strategy("s1")

    db2 = Database(path=tmp_path / "target.duckdb")
    db2.connect()
    svc2 = WorkspaceService(db2)
    svc2.import_strategy(bundle, now=NOW)

    restored = svc2.export_strategy("s1")
    assert restored.strategy == bundle.strategy
    assert set(restored.rules) == set(bundle.rules)
    assert set(restored.formulas) == set(bundle.formulas)
    db2.close()


def test_import_topological_order_formula_then_rule_then_strategy(svc) -> None:
    formula = Formula(id="base_metric", name="base", version="1", expression=ConstantOperand(1))
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FormulaOperand("base_metric"), ">", FactorOperand("per", "per")),
    )
    strategy = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("per"),), universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    bundle = StrategyBundle(strategy=strategy, rules=(rule,), formulas=(formula,))
    svc.import_strategy(bundle, now=NOW)  # 예외 없이 위상 순서로 저장됨
    assert svc.get_formula("base_metric") is not None
    assert svc.get_rule("entry_rule") is not None
    assert svc.get_strategy("s1") is not None


def test_import_dangling_reference_rejected(svc) -> None:
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(FormulaOperand("does_not_exist"), ">", FactorOperand("per", "per")),
    )
    strategy = StrategyDefinition(
        id="s1", name="s1", version="1",
        factor_refs=(FactorRef("per"),), universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    bundle = StrategyBundle(strategy=strategy, rules=(rule,), formulas=())
    with pytest.raises(DefinitionValidationError):
        svc.import_strategy(bundle, now=NOW)


def test_import_same_content_idempotent(svc) -> None:
    _build_strategy_with_formula(svc, "s1")
    bundle = svc.export_strategy("s1")
    svc.import_strategy(bundle, now=LATER, on_conflict="reject")  # 동일 내용 → 멱등 통과
    assert svc.get_strategy("s1") == bundle.strategy


def test_import_different_content_rejected_by_default(svc) -> None:
    _build_strategy_with_formula(svc, "s1")
    bundle = svc.export_strategy("s1")
    modified = StrategyBundle(
        strategy=StrategyDefinition(
            id="s1", name="변경됨", version="2",
            factor_refs=bundle.strategy.factor_refs, universe=bundle.strategy.universe,
            rule=bundle.strategy.rule,
        ),
        rules=bundle.rules, formulas=bundle.formulas,
    )
    with pytest.raises(WorkspaceError):
        svc.import_strategy(modified, now=LATER, on_conflict="reject")


def test_import_different_content_overwrite_replaces(svc) -> None:
    _build_strategy_with_formula(svc, "s1")
    bundle = svc.export_strategy("s1")
    modified = StrategyBundle(
        strategy=StrategyDefinition(
            id="s1", name="변경됨", version="2",
            factor_refs=bundle.strategy.factor_refs, universe=bundle.strategy.universe,
            rule=bundle.strategy.rule,
        ),
        rules=bundle.rules, formulas=bundle.formulas,
    )
    svc.import_strategy(modified, now=LATER, on_conflict="overwrite")
    assert svc.get_strategy("s1").name == "변경됨"


def test_import_overwrite_blocked_by_active_reference(svc) -> None:
    defn = _build_strategy_with_formula(svc, "s1")
    svc.activate("s1", now=NOW)
    bundle = svc.export_strategy("s1")
    modified_rule = Rule(
        id="entry_rule", name="entry 변경", version="1",
        root=Predicate(FactorOperand("sma", "sma"), ">", FactorOperand("per", "per")),
    )
    modified_bundle = StrategyBundle(
        strategy=defn, rules=(modified_rule,), formulas=bundle.formulas,
    )
    with pytest.raises(WorkspaceError):
        svc.import_strategy(modified_bundle, now=LATER, on_conflict="overwrite")
