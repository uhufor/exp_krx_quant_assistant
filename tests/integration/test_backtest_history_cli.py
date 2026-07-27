from __future__ import annotations

import re
from datetime import datetime

from typer.testing import CliRunner

from quant_krx.__main__ import app
from quant_krx.rule.definition import FactorOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.service import WorkspaceService

# 표 컬럼이 좁은 터미널에서 잘려 단언이 실패하지 않도록 폭을 고정한다(rich가 COLUMNS를 읽음).
runner = CliRunner(env={"COLUMNS": "200"})
NOW = datetime(2026, 1, 1, 0, 0, 0)


def _seed(tmp_path, monkeypatch, strategy_id: str = "hist_test") -> None:
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    svc.upsert_rule(
        Rule(
            id="entry_rule", name="entry", version="1",
            root=Predicate(
                FactorOperand("sma", "sma", {"window": 5}), ">",
                FactorOperand("sma", "sma", {"window": 20}),
            ),
        ),
        now=NOW,
    )
    svc.upsert_strategy(
        StrategyDefinition(
            id=strategy_id, name=strategy_id, version="1",
            factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
            universe=Universe(symbols=("005930",)),
            rule=RuleBinding(entry=("entry_rule",)),
        ),
        now=NOW,
    )
    db.close()


def _backtest(*extra: str, strategy_id: str = "hist_test"):
    return runner.invoke(
        app, ["strategy-backtest", strategy_id, "--data-source", "fixture", *extra]
    )


def _run_id_from(stdout: str) -> str:
    match = re.search(r"run_id=(\S+?)[,)\s]", stdout + " ")
    assert match, f"stdout에서 run_id를 찾지 못했습니다: {stdout}"
    return match.group(1)


def test_backtest_reports_saved_run_id(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = _backtest()
    assert result.exit_code == 0
    assert "실행 이력 저장됨" in result.stdout


def test_rerun_reports_cache_reuse(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    _backtest()
    result = _backtest()
    assert result.exit_code == 0
    assert "저장된 결과 재사용" in result.stdout
    assert "총수익률" in result.stdout, "캐시 히트에서도 지표 표는 동일하게 출력되어야 한다"


def test_no_cache_flag_forces_recomputation(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    _backtest()
    result = _backtest("--no-cache")
    assert result.exit_code == 0
    assert "실행 이력 저장됨" in result.stdout
    assert "저장된 결과 재사용" not in result.stdout


def test_backtest_list_shows_saved_runs(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    _backtest()
    result = runner.invoke(app, ["backtest-list"])
    assert result.exit_code == 0
    assert "hist_test" in result.stdout
    assert "총수익률" in result.stdout


def test_backtest_list_empty_is_not_an_error(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = runner.invoke(app, ["backtest-list"])
    assert result.exit_code == 0
    assert "이력이 없습니다" in result.stdout


def test_backtest_show_displays_parameters_and_metrics(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    run_id = _run_id_from(_backtest().stdout)

    result = runner.invoke(app, ["backtest-show", run_id])
    assert result.exit_code == 0
    assert "005930" in result.stdout
    assert "총수익률" in result.stdout
    assert "데이터 지문" in result.stdout


def test_backtest_show_missing_run_fails_clearly(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    result = runner.invoke(app, ["backtest-show", "no-such-run"])
    assert result.exit_code != 0
    assert "찾을 수 없습니다" in result.stdout
    assert "Traceback" not in result.stdout


def test_backtest_compare_shows_both_runs(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    first = _run_id_from(_backtest().stdout)
    second = _run_id_from(_backtest("--no-cache").stdout)
    assert first != second

    result = runner.invoke(app, ["backtest-compare", first, second])
    assert result.exit_code == 0
    assert "백테스트 비교" in result.stdout
    assert "정의 지문이 동일합니다" in result.stdout


def test_backtest_compare_requires_two_runs(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    run_id = _run_id_from(_backtest().stdout)
    result = runner.invoke(app, ["backtest-compare", run_id])
    assert result.exit_code != 0
    assert "2개 이상" in result.stdout


def test_backtest_compare_missing_run_fails_clearly(monkeypatch, tmp_path):
    _seed(tmp_path, monkeypatch)
    run_id = _run_id_from(_backtest().stdout)
    result = runner.invoke(app, ["backtest-compare", run_id, "no-such-run"])
    assert result.exit_code != 0
    assert "no-such-run" in result.stdout
    assert "Traceback" not in result.stdout


# --- 포트폴리오 모드 (P1) ---


def _seed_portfolio(tmp_path, monkeypatch, **policy_kwargs) -> None:
    from quant_krx.strategy.definition import PortfolioPolicy

    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    db = Database(path=db_path)
    db.connect()
    svc = WorkspaceService(db)
    svc.upsert_rule(
        Rule(
            id="entry_rule", name="entry", version="1",
            root=Predicate(
                FactorOperand("sma", "sma", {"window": 5}), ">",
                FactorOperand("sma", "sma", {"window": 20}),
            ),
        ),
        now=NOW,
    )
    svc.upsert_strategy(
        StrategyDefinition(
            id="pf_test", name="pf_test", version="1",
            factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
            universe=Universe(symbols=("005930", "000660", "006400")),
            rule=RuleBinding(entry=("entry_rule",)),
            portfolio=PortfolioPolicy(**{"max_positions": 2, **policy_kwargs}),
        ),
        now=NOW,
    )
    db.close()


def test_portfolio_backtest_cli_shows_mode_and_weights(monkeypatch, tmp_path):
    _seed_portfolio(tmp_path, monkeypatch)
    result = _backtest(strategy_id="pf_test")

    assert result.exit_code == 0, result.stdout
    assert "포트폴리오 모드" in result.stdout
    assert "최대 2종목" in result.stdout
    assert "리밸런싱 배분" in result.stdout


def test_portfolio_backtest_cli_caches_like_per_symbol_mode(monkeypatch, tmp_path):
    _seed_portfolio(tmp_path, monkeypatch)
    _backtest(strategy_id="pf_test")
    result = _backtest(strategy_id="pf_test")

    assert "저장된 결과 재사용" in result.stdout
    assert "리밸런싱 배분" in result.stdout, "캐시 복원에도 배분이 남아 있어야 한다"


def test_backtest_show_reports_portfolio_mode(monkeypatch, tmp_path):
    _seed_portfolio(tmp_path, monkeypatch)
    run_id = _run_id_from(_backtest(strategy_id="pf_test").stdout)

    result = runner.invoke(app, ["backtest-show", run_id])
    assert result.exit_code == 0
    assert "포트폴리오" in result.stdout
    assert "리밸런싱 배분" in result.stdout
