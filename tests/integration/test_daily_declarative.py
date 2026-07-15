from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from quant_krx.config.settings import Settings
from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.data.fixture_fundamental import FixtureFundamentalAdapter
from quant_krx.jobs.daily import DailyJob
from quant_krx.rule.definition import ConstantOperand, FactorOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.service import WorkspaceService

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_ohlcv.csv"
AS_OF = date(2024, 12, 31)
NOW = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield db
    db.close()


@pytest.fixture
def test_settings(tmp_path):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text(yaml.dump({"symbols": ["005930", "000660"]}))
    s = Settings(
        duckdb_path=str(tmp_path / "test.duckdb"),
        watchlist_path=str(watchlist_path),
        report_dir=str(tmp_path / "reports"),
        log_level="DEBUG",
    )
    s.llm.mock = True
    return s


@pytest.fixture
def fixture_provider():
    return FixtureAdapter(fixture_path=FIXTURE_PATH)


def _make_job(test_settings, tmp_db, fixture_provider, fundamental_provider=None):
    return DailyJob(
        settings=test_settings, db=tmp_db, provider=fixture_provider, notifier=None,
        fundamental_provider=fundamental_provider,
    )


def test_seed_creates_and_activates_five_builtins(tmp_db, test_settings, fixture_provider):
    job = _make_job(test_settings, tmp_db, fixture_provider)
    result = job.run(dry_run=True, as_of=AS_OF)
    assert result.status == "ok"

    svc = WorkspaceService(tmp_db)
    active = svc.list_active()
    assert active == tuple(sorted(active))  # id 정렬
    for tid in ("ma_crossover", "rsi_breakout", "bollinger_band", "macd", "momentum"):
        assert tid in active


def test_seed_idempotent_preserves_user_deactivation(tmp_db, test_settings, fixture_provider):
    job = _make_job(test_settings, tmp_db, fixture_provider)
    job.run(dry_run=True, as_of=AS_OF)  # 최초 시드+활성화

    svc = WorkspaceService(tmp_db)
    svc.deactivate("momentum", now=NOW)

    job2 = _make_job(test_settings, tmp_db, fixture_provider)
    job2.run(dry_run=True, as_of=AS_OF)  # 재실행 — 시드는 이미 존재하므로 무변경

    assert svc.is_active("momentum") is False
    assert svc.is_active("ma_crossover") is True


def test_active_zero_strategies_fails_clearly(tmp_db, test_settings, fixture_provider):
    job = _make_job(test_settings, tmp_db, fixture_provider)
    job.run(dry_run=True, as_of=AS_OF)  # 시드 + 활성화

    svc = WorkspaceService(tmp_db)
    for tid in ("ma_crossover", "rsi_breakout", "bollinger_band", "macd", "momentum"):
        svc.deactivate(tid, now=NOW)

    job2 = _make_job(test_settings, tmp_db, fixture_provider)
    result = job2.run(dry_run=True, as_of=AS_OF)
    assert result.status == "error"
    assert any("활성 전략" in e for e in result.errors)


def test_universe_partial_symbols_extend_collection(tmp_db, test_settings, fixture_provider):
    svc = WorkspaceService(tmp_db)
    rule = Rule(
        id="extra_entry", name="extra", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="extra_strategy", name="extra_strategy", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
        universe=Universe(symbols=("006400",)),  # watchlist(005930,000660)에 없는 종목
        rule=RuleBinding(entry=("extra_entry",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    svc.activate("extra_strategy", now=NOW)

    job = _make_job(test_settings, tmp_db, fixture_provider)
    result = job.run(dry_run=True, as_of=AS_OF)
    assert result.status == "ok"
    assert result.symbol_count == 3  # watchlist 2 + universe 추가 1

    with tmp_db.cursor() as conn:
        row = conn.execute("SELECT count(*) FROM ohlcv_daily WHERE symbol='006400'").fetchone()
    assert row[0] > 0

    # FR-15/D5: 빈 universe(=watchlist) 전략은 다른 전략의 전용 universe 심볼(006400)로는
    # 실행되지 않는다 — 수집 대상 합집합(collect_symbols)과 실행 대상(watchlist)은 별개.
    with tmp_db.cursor() as conn:
        row = conn.execute(
            "SELECT count(*) FROM signals WHERE symbol='006400' AND strategy != 'extra_strategy'"
        ).fetchone()
    assert row[0] == 0


def test_ohlcv_only_active_set_skips_fundamental_fetch(tmp_db, test_settings, fixture_provider):
    calls = {"n": 0}

    class SpyFundamentalProvider(FixtureFundamentalAdapter):
        def fetch_valuation(self, symbols, start, end):
            calls["n"] += 1
            return super().fetch_valuation(symbols, start, end)

        def fetch_financials(self, symbols, start, end):
            calls["n"] += 1
            return super().fetch_financials(symbols, start, end)

    job = _make_job(
        test_settings, tmp_db, fixture_provider, fundamental_provider=SpyFundamentalProvider()
    )
    result = job.run(dry_run=True, as_of=AS_OF)
    assert result.status == "ok"
    assert calls["n"] == 0  # Built-in 5종은 전부 ohlcv-only


def test_valuation_required_strategy_triggers_fundamental_fetch(
    tmp_db, test_settings, fixture_provider
):
    svc = WorkspaceService(tmp_db)
    rule = Rule(
        id="per_entry", name="per_entry", version="1",
        root=Predicate(FactorOperand("per", "per"), ">", ConstantOperand(0)),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="per_strategy", name="per_strategy", version="1",
        factor_refs=(FactorRef("per"),), universe=Universe(),
        rule=RuleBinding(entry=("per_entry",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    svc.activate("per_strategy", now=NOW)

    calls = {"n": 0}

    class SpyFundamentalProvider(FixtureFundamentalAdapter):
        def fetch_valuation(self, symbols, start, end):
            calls["n"] += 1
            return super().fetch_valuation(symbols, start, end)

    job = _make_job(
        test_settings, tmp_db, fixture_provider, fundamental_provider=SpyFundamentalProvider()
    )
    result = job.run(dry_run=True, as_of=AS_OF)
    assert result.status == "ok"
    assert calls["n"] >= 1


def test_injected_now_makes_seed_activation_timestamp_deterministic(
    tmp_db, test_settings, fixture_provider
):
    # TR-R03-025/INV-3: DailyJob.run()에 now를 주입하면 전환 시드가 기록하는
    # strategy_activation.updated_at도 결정론이어야 한다(벽시계 datetime.utcnow() 의존 금지).
    job = _make_job(test_settings, tmp_db, fixture_provider)
    result = job.run(dry_run=True, as_of=AS_OF, now=NOW)
    assert result.status == "ok"

    with tmp_db.cursor() as conn:
        row = conn.execute(
            "SELECT updated_at FROM strategy_activation WHERE strategy_id='ma_crossover'"
        ).fetchone()
    assert row[0] == NOW


def test_strategy_symbol_failure_isolated_and_batch_completes(
    tmp_db, test_settings, fixture_provider
):
    svc = WorkspaceService(tmp_db)
    rule = Rule(
        id="bad_entry", name="bad_entry", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    svc.upsert_rule(rule, now=NOW)
    # 존재하지 않는 종목을 universe에 넣어 해당 전략×종목 조합에서 데이터 부재를 유발
    defn = StrategyDefinition(
        id="isolated_strategy", name="isolated_strategy", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
        universe=Universe(symbols=("999999",)),
        rule=RuleBinding(entry=("bad_entry",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    svc.activate("isolated_strategy", now=NOW)

    job = _make_job(test_settings, tmp_db, fixture_provider)
    result = job.run(dry_run=True, as_of=AS_OF)
    # 존재하지 않는 종목 하나가 실패해도 배치 전체는 완주(ok)한다
    assert result.status == "ok"
    assert result.signal_count > 0  # 나머지(Built-in 5종 × watchlist)는 정상 처리됨
