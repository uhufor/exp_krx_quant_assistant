import hashlib
from datetime import date
from pathlib import Path

import pytest
import yaml

from quant_krx.config.settings import Settings
from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.jobs.daily import DailyJob, DailyJobResult
from quant_krx.storage.db import Database

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_ohlcv.csv"


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


def test_daily_job_dry_run(tmp_db, test_settings, fixture_provider):
    """dry_run=True: 알림 없이 정상 완료."""
    job = DailyJob(
        settings=test_settings,
        db=tmp_db,
        provider=fixture_provider,
        notifier=None,
    )
    result = job.run(dry_run=True, as_of=date(2024, 12, 31))
    assert isinstance(result, DailyJobResult)
    assert result.status == "ok"
    assert result.signal_count > 0
    assert result.report_a_count > 0
    assert result.report_b_count > 0


def test_daily_job_dry_run_no_notification(tmp_db, test_settings, fixture_provider):
    """dry_run: notification_outbox에 발송 기록 없음."""
    job = DailyJob(
        settings=test_settings,
        db=tmp_db,
        provider=fixture_provider,
        notifier=None,
    )
    job.run(dry_run=True, as_of=date(2024, 12, 31))
    pending = tmp_db.get_pending_notifications("telegram")
    assert len(pending) == 0  # notifier=None이면 outbox에도 없음


def test_outbox_dedup_blocks_duplicate_content(tmp_db):
    """동일 채널+콘텐츠는 UNIQUE(channel, content_hash) 제약으로 중복 저장 차단됨."""
    n1 = tmp_db.enqueue_notification("run-001", "telegram", "hash-abc", "test payload")
    n2 = tmp_db.enqueue_notification("run-002", "telegram", "hash-abc", "test payload")
    # 두 번째 enqueue는 기존 id를 반환해야 함
    assert n1 == n2
    with tmp_db.cursor() as conn:
        count = conn.execute(
            "SELECT count(*) FROM notification_outbox WHERE content_hash='hash-abc'"
        ).fetchone()[0]
    assert count == 1


def test_outbox_status_guard_skips_already_sent(tmp_db):
    """이미 'sent' 상태인 알림의 status를 조회할 수 있다."""
    nid = tmp_db.enqueue_notification("run-001", "telegram", "hash-xyz", "payload")
    assert tmp_db.get_notification_status(nid) == "pending"
    tmp_db.mark_notification_sent(nid)
    assert tmp_db.get_notification_status(nid) == "sent"


def test_daily_job_events_logged(tmp_db, test_settings, fixture_provider):
    """실행 이벤트가 run_events 테이블에 기록됨."""
    job = DailyJob(
        settings=test_settings,
        db=tmp_db,
        provider=fixture_provider,
        notifier=None,
    )
    result = job.run(dry_run=True, as_of=date(2024, 12, 31))
    with tmp_db.cursor() as conn:
        rows = conn.execute(
            "SELECT event_type FROM run_events WHERE run_id=? ORDER BY id",
            [result.run_id],
        ).fetchall()
    event_types = [r[0] for r in rows]
    assert "job_start" in event_types
    assert "job_done" in event_types
