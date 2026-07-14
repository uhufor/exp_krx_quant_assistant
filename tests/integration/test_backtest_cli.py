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


def test_strategy_backtest_with_benchmark_option_reports_relative_performance(
    monkeypatch, tmp_path
):
    # FR-11/12: --benchmark 지정 시 크래시 없이 벤치마크 상대 성과가 표에 함께 산출되어야 한다.
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    rule = Rule(
        id="entry_rule3", name="entry", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="benchmark_test", name="benchmark_test", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
        universe=Universe(symbols=("005930",)),
        rule=RuleBinding(entry=("entry_rule3",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    db.close()

    result = runner.invoke(
        app,
        ["strategy-backtest", "benchmark_test", "--data-source", "fixture", "--benchmark", "KOSPI"],
    )
    assert result.exit_code == 0
    assert "벤치마크" in result.stdout


def test_strategy_backtest_benchmark_fetch_failure_falls_back_gracefully(monkeypatch, tmp_path):
    # 벤치마크 수집 실패는 경고만 남기고 백테스트 자체는 계속 완주해야 한다.
    from quant_krx.data.fixture_adapter import FixtureAdapter

    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    rule = Rule(
        id="entry_rule4", name="entry", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="benchmark_fail_test", name="benchmark_fail_test", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
        universe=Universe(symbols=("005930",)),
        rule=RuleBinding(entry=("entry_rule4",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    db.close()

    def _raise_fetch_benchmark(self, *args, **kwargs):
        raise RuntimeError("강제 실패(테스트용)")

    monkeypatch.setattr(FixtureAdapter, "fetch_benchmark", _raise_fetch_benchmark)

    result = runner.invoke(
        app,
        ["strategy-backtest", "benchmark_fail_test", "--data-source", "fixture",
         "--benchmark", "KOSPI"],
    )
    assert result.exit_code == 0
    assert "벤치마크 'KOSPI' 수집 실패" in result.stdout
    assert "총수익률" in result.stdout


def test_strategy_show_missing_lists_available_ids(monkeypatch, tmp_path):
    # TR-R03-024: 미존재 id 오류는 사용 가능한 id 목록을 힌트로 포함해야 한다.
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    defn = StrategyDefinition(
        id="known_strategy", name="known", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    svc.upsert_strategy(defn, now=NOW)
    db.close()

    result = runner.invoke(app, ["strategy-show", "no_such_strategy"])
    assert result.exit_code != 0
    assert "known_strategy" in result.stdout


def test_strategy_backtest_evaluation_failure_reported_without_traceback(monkeypatch, tmp_path):
    # M2 후속: build_signals가 실행 시점에 WorkspaceError 계열을 던지면 CLI가
    # 스택트레이스를 노출하지 않고 한국어 사유 + non-zero로 마감해야 한다(TR-R03-024).
    from quant_krx.workspace.errors import WorkspaceError
    from quant_krx.workspace.service import WorkspaceService as SvcCls

    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    rule = Rule(
        id="entry_rule2", name="entry", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="fail_test", name="fail_test", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
        universe=Universe(symbols=("005930",)),
        rule=RuleBinding(entry=("entry_rule2",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    db.close()

    def _raise_backtest(self, *args, **kwargs):
        raise WorkspaceError("강제 실패(테스트용)")

    monkeypatch.setattr(SvcCls, "backtest", _raise_backtest)

    result = runner.invoke(app, ["strategy-backtest", "fail_test", "--data-source", "fixture"])
    assert result.exit_code != 0
    assert "백테스트 실패" in result.stdout
    assert "Traceback" not in result.stdout
