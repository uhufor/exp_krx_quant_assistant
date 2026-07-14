from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from quant_krx.__main__ import app
from quant_krx.rule.definition import FactorOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.service import WorkspaceService

runner = CliRunner()
NOW = datetime(2026, 1, 1, 0, 0, 0)


def test_strategy_backtest_missing_strategy_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    result = runner.invoke(app, ["strategy-backtest", "no_such_strategy"])
    assert result.exit_code != 0


def test_strategy_backtest_draft_strategy_rejected(monkeypatch, tmp_path):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    defn = StrategyDefinition(
        id="draft1", name="draft1", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    svc.upsert_strategy(defn, now=NOW)
    db.close()

    result = runner.invoke(app, ["strategy-backtest", "draft1"])
    assert result.exit_code != 0


def test_strategy_backtest_fixture_happy_path(monkeypatch, tmp_path):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="cli_test", name="cli_test", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
        universe=Universe(symbols=("005930",)),
        rule=RuleBinding(entry=("entry_rule",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    db.close()

    result = runner.invoke(app, ["strategy-backtest", "cli_test", "--data-source", "fixture"])
    assert result.exit_code == 0
    assert "총수익률" in result.stdout
    assert "MDD" in result.stdout
