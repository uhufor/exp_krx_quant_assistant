from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from quant_krx.config.settings import Settings
from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.jobs.daily import DailyJob
from quant_krx.rule.definition import FactorOperand, Predicate, Rule
from quant_krx.screening.definition import RankPredicate, ScanUniverse, ScreeningCondition
from quant_krx.screening.service import ScreeningService
from quant_krx.signals.classifier import PORTFOLIO_SYMBOL
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import (
    FactorRef,
    PortfolioPolicy,
    RuleBinding,
    StrategyDefinition,
    Universe,
)
from quant_krx.workspace.service import WorkspaceService

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_ohlcv.csv"
AS_OF = date(2024, 12, 18)
NOW = datetime(2026, 1, 1, 0, 0, 0)
# fixture 5종목 중 watchlist에는 2종목만 둔다 — 동적 유니버스가 watchlist로 대체되는지
# 판별하려면 둘의 종목 집합이 달라야 한다.
WATCHLIST = ["005930", "000660"]


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield db
    db.close()


@pytest.fixture
def test_settings(tmp_path):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text(yaml.dump({"symbols": WATCHLIST}))
    s = Settings(
        duckdb_path=str(tmp_path / "test.duckdb"),
        watchlist_path=str(watchlist_path),
        report_dir=str(tmp_path / "reports"),
        log_level="DEBUG",
    )
    s.llm.mock = True
    return s


@pytest.fixture
def provider():
    return FixtureAdapter(fixture_path=FIXTURE_PATH)


def _job(test_settings, tmp_db, provider) -> DailyJob:
    return DailyJob(
        settings=test_settings, db=tmp_db, provider=provider, notifier=None,
    )


def _seed_rule(svc: WorkspaceService) -> None:
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


def _seed_portfolio_strategy(tmp_db, *, universe: Universe, sid: str = "pf") -> None:
    svc = WorkspaceService(tmp_db)
    _seed_rule(svc)
    svc.upsert_strategy(
        StrategyDefinition(
            id=sid, name=f"{sid} 전략", version="1",
            factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
            universe=universe,
            rule=RuleBinding(entry=("entry_rule",)),
            portfolio=PortfolioPolicy(max_positions=2, rebalance="monthly"),
        ),
        now=NOW,
    )


def _seed_screening(tmp_db, provider) -> None:
    ScreeningService(tmp_db, provider).upsert_condition(
        ScreeningCondition(
            id="tv_top2", name="거래대금 Top2", version="1",
            universe=ScanUniverse(market="KRX", exclusion_filters=frozenset()),
            root=RankPredicate(
                factor_id="trading_value", column="trading_value",
                rank_metric="desc", top_n=2,
            ),
        ),
        now=NOW,
    )


def _activate_only(tmp_db, sid: str) -> None:
    """Built-in 시드가 활성화한 5종을 끄고 대상 전략만 남긴다."""
    svc = WorkspaceService(tmp_db)
    for other in svc.list_active():
        if other != sid:
            svc.deactivate(other, now=NOW)
    svc.activate(sid, now=NOW)


def _signals(tmp_db, run_id: str) -> list[dict]:
    with tmp_db.cursor() as conn:
        rows = conn.execute(
            "SELECT symbol, signal_type, strategy FROM signals WHERE run_id=?", [run_id]
        ).fetchall()
    return [{"symbol": r[0], "signal_type": r[1], "strategy": r[2]} for r in rows]


# --- 정적 유니버스 포트폴리오 ---


def test_portfolio_strategy_emits_single_account_signal(tmp_db, test_settings, provider):
    """포트폴리오 전략은 종목별이 아니라 계좌 단위 신호 1건을 낸다."""
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)  # 시드
    _seed_portfolio_strategy(
        tmp_db, universe=Universe(symbols=("005930", "000660", "006400"))
    )
    _activate_only(tmp_db, "pf")

    result = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    assert result.status == "ok", result.errors
    signals = _signals(tmp_db, result.run_id)
    assert len(signals) == 1
    assert signals[0]["symbol"] == PORTFOLIO_SYMBOL
    assert signals[0]["signal_type"] in ("rebalance", "hold")


def test_portfolio_reports_are_generated(tmp_db, test_settings, provider):
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    _seed_portfolio_strategy(tmp_db, universe=Universe(symbols=("005930", "000660")))
    _activate_only(tmp_db, "pf")

    result = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    assert result.report_a_count == 1
    assert result.report_b_count == 1

    with tmp_db.cursor() as conn:
        contents = [
            r[0] for r in conn.execute(
                "SELECT content FROM reports WHERE run_id=? AND report_type='A'",
                [result.run_id],
            ).fetchall()
        ]
    assert contents
    assert "포트폴리오 리포트" in contents[0]
    assert "__portfolio__" not in contents[0]


# --- 동적 유니버스 (이번 결함의 회귀 테스트) ---


def test_dynamic_universe_is_not_replaced_by_watchlist(tmp_db, test_settings, provider):
    """동적 유니버스 전략이 watchlist로 조용히 대체되면 안 된다(R05가 고친 결함).

    스크리닝은 거래대금 Top2를 뽑고, watchlist는 그와 다른 2종목이다. 대체가 일어나면
    수집 대상이 watchlist와 정확히 같아지므로 종목 수로 판별할 수 있다.
    """
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    _seed_screening(tmp_db, provider)
    _seed_portfolio_strategy(
        tmp_db, universe=Universe(kind="screening", screening_id="tv_top2")
    )
    _activate_only(tmp_db, "pf")

    result = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    assert result.status == "ok", result.errors
    # 수집 대상 = watchlist ∪ 스크리닝 종목. 스크리닝이 watchlist에 없는 종목을 뽑았다면
    # 총 종목 수가 watchlist보다 많아진다.
    assert result.symbol_count > len(WATCHLIST), (
        "동적 유니버스 종목이 수집 대상에 포함되지 않았다(watchlist로 대체된 것으로 의심)"
    )


def test_dynamic_universe_produces_portfolio_signal(tmp_db, test_settings, provider):
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    _seed_screening(tmp_db, provider)
    _seed_portfolio_strategy(
        tmp_db, universe=Universe(kind="screening", screening_id="tv_top2")
    )
    _activate_only(tmp_db, "pf")

    result = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    signals = _signals(tmp_db, result.run_id)
    assert len(signals) == 1
    assert signals[0]["symbol"] == PORTFOLIO_SYMBOL


def test_missing_screening_condition_isolates_failure(tmp_db, test_settings, provider):
    """스크리닝 조건이 없어도 잡 전체가 죽지 않고 해당 전략만 실패로 기록된다."""
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    _seed_portfolio_strategy(
        tmp_db, universe=Universe(kind="screening", screening_id="no_such")
    )
    svc = WorkspaceService(tmp_db)
    svc.activate("pf", now=NOW)  # Built-in 5종은 그대로 둔 채 함께 활성

    result = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    assert result.status == "ok"
    assert any("pf" in e for e in result.errors)
    # 나머지 전략(Built-in)의 종목별 신호는 정상 생성된다.
    assert result.signal_count > 0


# --- 혼합·회귀 ---


def test_portfolio_and_per_symbol_strategies_coexist(tmp_db, test_settings, provider):
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    _seed_portfolio_strategy(tmp_db, universe=Universe(symbols=("005930", "000660")))
    WorkspaceService(tmp_db).activate("pf", now=NOW)  # Built-in 5종 + pf

    result = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    signals = _signals(tmp_db, result.run_id)
    portfolio = [s for s in signals if s["symbol"] == PORTFOLIO_SYMBOL]
    per_symbol = [s for s in signals if s["symbol"] != PORTFOLIO_SYMBOL]
    assert len(portfolio) == 1
    assert per_symbol, "종목별 전략 신호도 함께 생성되어야 한다"


def test_per_symbol_only_run_is_unchanged(tmp_db, test_settings, provider):
    """포트폴리오 전략이 없으면 기존 동작 그대로(회귀)."""
    result = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    assert result.status == "ok"
    signals = _signals(tmp_db, result.run_id)
    assert signals
    assert all(s["symbol"] != PORTFOLIO_SYMBOL for s in signals)


def test_dry_run_writes_no_outbox(tmp_db, test_settings, provider):
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    _seed_portfolio_strategy(tmp_db, universe=Universe(symbols=("005930", "000660")))
    _activate_only(tmp_db, "pf")

    result = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    with tmp_db.cursor() as conn:
        count = conn.execute(
            "SELECT count(*) FROM notification_outbox WHERE run_id=?", [result.run_id]
        ).fetchone()[0]
    assert count == 0


def test_portfolio_signal_is_deterministic(tmp_db, test_settings, provider):
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    _seed_portfolio_strategy(tmp_db, universe=Universe(symbols=("005930", "000660")))
    _activate_only(tmp_db, "pf")

    first = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    second = _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    a = _signals(tmp_db, first.run_id)[0]
    b = _signals(tmp_db, second.run_id)[0]
    assert a["signal_type"] == b["signal_type"]


def test_show_reports_does_not_leak_pseudo_key(tmp_db, test_settings, provider, monkeypatch):
    """CLI 표·패널 제목에도 의사 키가 노출되면 안 된다(리포트 본문만 고치면 놓치는 지점)."""
    from typer.testing import CliRunner

    from quant_krx.__main__ import app

    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)
    _seed_portfolio_strategy(tmp_db, universe=Universe(symbols=("005930", "000660")))
    _activate_only(tmp_db, "pf")
    _job(test_settings, tmp_db, provider).run(dry_run=True, as_of=AS_OF)

    monkeypatch.setenv("DUCKDB_PATH", str(test_settings.duckdb_path))
    result = CliRunner(env={"COLUMNS": "200"}).invoke(app, ["show-reports"])

    assert result.exit_code == 0, result.stdout
    assert PORTFOLIO_SYMBOL not in result.stdout
    assert "포트폴리오" in result.stdout


# --- run-daily CLI 옵션 (검증 수단) ---


def _cli(monkeypatch, test_settings, *args):
    from typer.testing import CliRunner

    from quant_krx.__main__ import app

    monkeypatch.setenv("DUCKDB_PATH", str(test_settings.duckdb_path))
    monkeypatch.setenv("WATCHLIST_PATH", str(test_settings.watchlist_path))
    monkeypatch.setenv("LLM_MOCK", "true")
    return CliRunner(env={"COLUMNS": "200"}).invoke(app, list(args))


def test_run_daily_accepts_as_of_and_fixture(monkeypatch, test_settings, tmp_db, provider):
    """데일리를 네트워크 없이 특정 시점으로 재현할 수 있어야 한다(오프라인 검증 수단)."""
    result = _cli(
        monkeypatch, test_settings,
        "run-daily", "--dry-run", "--data-source", "fixture", "--as-of", "2024-12-02",
    )
    assert result.exit_code == 0, result.stdout
    assert "ok" in result.stdout


def test_run_daily_rejects_bad_as_of(monkeypatch, test_settings):
    result = _cli(
        monkeypatch, test_settings, "run-daily", "--data-source", "fixture", "--as-of", "2024/12/02"
    )
    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.stdout
    assert "Traceback" not in result.stdout


def test_run_daily_rejects_unknown_data_source(monkeypatch, test_settings):
    result = _cli(monkeypatch, test_settings, "run-daily", "--data-source", "yahoo")
    assert result.exit_code != 0
    assert "알 수 없는" in result.stdout


def test_run_daily_as_of_changes_report_section(monkeypatch, test_settings, tmp_db, provider):
    """리밸런싱일과 평일의 리포트 섹션이 달라야 한다(지난 지시 반복 방지 확인)."""
    _cli(monkeypatch, test_settings, "run-daily", "--data-source", "fixture",
         "--as-of", "2024-12-02")
    _seed_portfolio_strategy(tmp_db, universe=Universe(symbols=("005930", "000660", "006400")))
    _activate_only(tmp_db, "pf")

    _cli(monkeypatch, test_settings, "run-daily", "--data-source", "fixture",
         "--as-of", "2024-12-02")
    on_day = _cli(monkeypatch, test_settings, "show-reports", "--type", "A").stdout

    _cli(monkeypatch, test_settings, "run-daily", "--data-source", "fixture",
         "--as-of", "2024-12-18")
    off_day = _cli(monkeypatch, test_settings, "show-reports", "--type", "A").stdout

    assert "매매 지시" in on_day or "현재 목표 배분" in on_day
    assert "현재 목표 배분" in off_day
