import uuid
from datetime import date, datetime

import pandas as pd
import pytest

from quant_krx.storage.db import Database


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield db
    db.close()


@pytest.fixture
def sample_ohlcv():
    dates = pd.bdate_range("2024-01-02", periods=10, freq="B")
    df = pd.DataFrame({
        "date": [d.date() for d in dates],
        "open": [50000.0] * 10,
        "high": [52000.0] * 10,
        "low": [48000.0] * 10,
        "close": [51000.0] * 10,
        "volume": [1000000] * 10,
    })
    return df


def test_upsert_ohlcv(tmp_db, sample_ohlcv):
    n = tmp_db.upsert_ohlcv("005930", sample_ohlcv, "FinanceDataReader", datetime.utcnow())
    assert n == 10
    result = tmp_db.fetch_ohlcv("005930", date(2024, 1, 1), date(2024, 12, 31))
    assert len(result) == 10


def test_upsert_ohlcv_idempotent(tmp_db, sample_ohlcv):
    tmp_db.upsert_ohlcv("005930", sample_ohlcv, "FinanceDataReader", datetime.utcnow())
    n2 = tmp_db.upsert_ohlcv("005930", sample_ohlcv, "FinanceDataReader", datetime.utcnow())
    result = tmp_db.fetch_ohlcv("005930", date(2024, 1, 1), date(2024, 12, 31))
    assert len(result) == 10  # 중복 없음


def test_notification_outbox_enqueue(tmp_db):
    run_id = f"20240102-{uuid.uuid4().hex[:8]}"
    nid = tmp_db.enqueue_notification(run_id, "telegram", "hash1", "payload1")
    assert nid is not None
    pending = tmp_db.get_pending_notifications("telegram")
    assert len(pending) == 1
    assert pending.iloc[0]["run_id"] == run_id


def test_notification_outbox_no_duplicate(tmp_db):
    run_id = f"20240102-{uuid.uuid4().hex[:8]}"
    id1 = tmp_db.enqueue_notification(run_id, "telegram", "same_hash", "payload")
    id2 = tmp_db.enqueue_notification(run_id, "telegram", "same_hash", "payload")
    pending = tmp_db.get_pending_notifications("telegram")
    assert len(pending) == 1  # 중복 enqueue 시 1건만


def test_notification_mark_sent(tmp_db):
    run_id = f"20240102-{uuid.uuid4().hex[:8]}"
    nid = tmp_db.enqueue_notification(run_id, "telegram", "hash2", "payload2")
    tmp_db.mark_notification_sent(nid)
    pending = tmp_db.get_pending_notifications("telegram")
    assert len(pending) == 0


def test_notification_mark_failed_and_retry(tmp_db):
    run_id = f"20240102-{uuid.uuid4().hex[:8]}"
    nid = tmp_db.enqueue_notification(run_id, "telegram", "hash3", "payload3")
    tmp_db.mark_notification_failed(nid, "timeout")
    with tmp_db.cursor() as conn:
        row = conn.execute(
            "SELECT status, retry_count, error_msg FROM notification_outbox WHERE id=?", [nid]
        ).fetchone()
    assert row[0] == "failed"
    assert row[1] == 1
    assert row[2] == "timeout"


def test_log_event(tmp_db):
    tmp_db.log_event("run-001", "fetch_start", "Fetching OHLCV")
    with tmp_db.cursor() as conn:
        rows = conn.execute("SELECT * FROM run_events WHERE run_id='run-001'").fetchall()
    assert len(rows) == 1
