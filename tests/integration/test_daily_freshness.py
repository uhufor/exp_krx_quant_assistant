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
AS_OF = date(2024, 12, 18)
NOW = datetime(2026, 1, 1)


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(path=tmp_path / "t.duckdb")
    db.connect()
    yield db
    db.close()


@pytest.fixture
def settings(tmp_path):
    wl = tmp_path / "watchlist.yaml"
    wl.write_text(yaml.dump({"symbols": ["005930", "000660"]}))
    s = Settings(
        duckdb_path=str(tmp_path / "t.duckdb"),
        watchlist_path=str(wl),
        report_dir=str(tmp_path / "reports"),
    )
    s.llm.mock = True
    return s


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    monkeypatch.setenv("KRX_ID", "x")
    monkeypatch.setenv("KRX_PW", "x")
    monkeypatch.setenv("DART_API_KEY", "x")


def _job(settings, db, fundamental=None) -> DailyJob:
    return DailyJob(
        settings=settings, db=db, provider=FixtureAdapter(fixture_path=FIXTURE_PATH),
        notifier=None, fundamental_provider=fundamental or FixtureFundamentalAdapter(),
    )


def _seed_valuation_strategy(db) -> None:
    """밸류에이션이 필요한 전략만 활성화 — 신선도 점검이 valuation을 대상으로 삼게 한다."""
    svc = WorkspaceService(db)
    svc.upsert_rule(
        Rule(
            id="per_rule", name="per", version="1",
            root=Predicate(FactorOperand("per", "per", {}), "<", ConstantOperand(15.0)),
        ),
        now=NOW,
    )
    svc.upsert_strategy(
        StrategyDefinition(
            id="val_strategy", name="저PER 전략", version="1",
            factor_refs=(FactorRef("per"),),
            universe=Universe(symbols=("005930",)),
            rule=RuleBinding(entry=("per_rule",)),
        ),
        now=NOW,
    )
    for sid in svc.list_active():
        if sid != "val_strategy":
            svc.deactivate(sid, now=NOW)
    svc.activate("val_strategy", now=NOW)


def _reports(db, run_id: str, rtype: str = "A") -> list[str]:
    with db.cursor() as conn:
        rows = conn.execute(
            "SELECT content FROM reports WHERE run_id=? AND report_type=?", [run_id, rtype]
        ).fetchall()
    return [r[0] for r in rows]


class _FailingFundamental(FixtureFundamentalAdapter):
    """밸류에이션 수집이 실패하는 상황(자격증명 만료·API 장애 등) 재현."""

    def fetch_valuation(self, symbols, start, end):
        raise RuntimeError("수집 실패(테스트)")


def test_fundamental_fetch_failure_does_not_kill_job(tmp_db, settings):
    """펀더멘털 수집 실패로 잡 전체가 죽으면 안 된다.

    KRX 세션 만료나 DART 장애 하나로 매일 잡이 멈추면 안 되므로, 백테스트 경로와 같은
    원칙으로 흡수하고 결측은 신선도 경고로 드러낸다.
    """
    _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)  # 시드
    _seed_valuation_strategy(tmp_db)

    result = _job(settings, tmp_db, fundamental=_FailingFundamental()).run(
        dry_run=True, as_of=AS_OF
    )

    assert result.status == "ok"
    assert any("펀더멘털 수집 실패" in e for e in result.errors)


def test_warning_reaches_user_even_when_no_signals(tmp_db, settings):
    """신호가 0건이면 경고를 실을 리포트가 없다 — 폴백 알림이 나가야 한다.

    데이터가 없어 전 전략이 실패한 상황이 정확히 이 경우다. 폴백이 없으면 "아무 알림도
    안 왔는데 이유를 모르는" 침묵이 된다.
    """
    _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)
    _seed_valuation_strategy(tmp_db)

    job = _job(settings, tmp_db, fundamental=_FailingFundamental())
    sent: list[str] = []
    job._notifier = type("N", (), {"send": lambda self, rid, msg: sent.append(msg) or "id"})()

    result = job.run(dry_run=False, as_of=AS_OF)

    assert result.signal_count == 0
    assert sent, "신호가 없어도 데이터 경고는 전달되어야 한다"
    assert "데이터 상태 경고" in sent[0]
    assert "밸류에이션" in sent[0]


def test_warning_appears_in_report_when_signals_exist(tmp_db, settings):
    """신호가 있으면 각 리포트 상단에 경고 한 줄이 붙는다."""
    _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)  # Built-in(ohlcv만) 활성 상태

    # ohlcv 수집 실패를 만들어 경고를 유발한다(전략 실행 자체는 나머지 종목으로 계속).
    class _PartialProvider(FixtureAdapter):
        def fetch_ohlcv(self, symbol, start, end, interval="1d"):
            if symbol == "000660":
                raise RuntimeError("수집 실패(테스트)")
            return super().fetch_ohlcv(symbol, start, end, interval)

    job = DailyJob(
        settings=settings, db=tmp_db, provider=_PartialProvider(fixture_path=FIXTURE_PATH),
        notifier=None, fundamental_provider=FixtureFundamentalAdapter(),
    )
    result = job.run(dry_run=True, as_of=AS_OF)

    contents = _reports(tmp_db, result.run_id)
    assert contents
    assert any("데이터 상태" in c for c in contents)
    assert any("시세 수집 실패" in c for c in contents)


def test_no_warning_when_data_is_fresh(tmp_db, settings):
    """정상일 때는 리포트에 아무것도 추가하지 않는다(평소 리포트가 길어지지 않도록)."""
    _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)
    _seed_valuation_strategy(tmp_db)

    result = _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)

    contents = _reports(tmp_db, result.run_id)
    assert contents
    assert not any("데이터 상태" in c for c in contents)


def test_unused_data_staleness_is_not_warned(tmp_db, settings):
    """전략이 쓰지 않는 데이터의 지연은 경고하지 않는다 — 잡음이 되기 때문."""
    result = _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)  # Built-in 5종(ohlcv만)

    contents = _reports(tmp_db, result.run_id)
    assert contents
    # 재무제표가 비어 있어도 ohlcv만 쓰는 전략에는 무관하므로 경고가 없어야 한다.
    assert not any("재무제표" in c for c in contents)


def test_warning_is_logged_as_run_event(tmp_db, settings):
    _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)
    _seed_valuation_strategy(tmp_db)

    result = _job(settings, tmp_db, fundamental=_FailingFundamental()).run(
        dry_run=True, as_of=AS_OF
    )

    with tmp_db.cursor() as conn:
        events = conn.execute(
            "SELECT count(*) FROM run_events WHERE run_id=? AND event_type='freshness_warn'",
            [result.run_id],
        ).fetchone()[0]
    assert events == 1


# --- data-health CLI ---


def _cli(monkeypatch, settings, *args):
    from typer.testing import CliRunner

    from quant_krx.__main__ import app

    monkeypatch.setenv("DUCKDB_PATH", str(settings.duckdb_path))
    monkeypatch.setenv("WATCHLIST_PATH", str(settings.watchlist_path))
    return CliRunner(env={"COLUMNS": "200"}).invoke(app, list(args))


def test_data_health_reports_issues(tmp_db, settings, monkeypatch):
    result = _cli(monkeypatch, settings, "data-health", "--as-of", "2024-12-18")
    assert result.exit_code == 0, result.stdout
    assert "데이터 신선도" in result.stdout


def test_data_health_accepts_symbols_and_skips(tmp_db, settings, monkeypatch):
    result = _cli(
        monkeypatch, settings, "data-health",
        "--symbols", "005930", "--as-of", "2024-12-18", "--skip-financials",
    )
    assert result.exit_code == 0
    assert "재무제표" not in result.stdout


def test_data_health_rejects_bad_date(tmp_db, settings, monkeypatch):
    result = _cli(monkeypatch, settings, "data-health", "--as-of", "2024/12/18")
    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.stdout
    assert "Traceback" not in result.stdout


def test_data_health_shows_ok_when_fresh(tmp_db, settings, monkeypatch):
    """수집이 끝난 뒤에는 정상으로 표시된다."""
    _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)
    _seed_valuation_strategy(tmp_db)
    _job(settings, tmp_db).run(dry_run=True, as_of=AS_OF)

    result = _cli(
        monkeypatch, settings, "data-health",
        "--as-of", "2024-12-18", "--skip-financials",
    )
    assert result.exit_code == 0
    assert "정상" in result.stdout
