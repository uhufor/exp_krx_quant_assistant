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


def test_schema_tables_all_created(tmp_path):
    """DDL에 선언된 테이블이 connect() 후 모두 존재해야 한다(신규 테이블 배선 누락 방지)."""
    from quant_krx.storage.db import _SCHEMA_TABLES

    db = Database(path=tmp_path / "schema.duckdb")
    db.connect()
    try:
        assert db._missing_tables() == set()
        assert "backtest_runs" in _SCHEMA_TABLES
    finally:
        db.close()


def test_concurrent_connect_on_fresh_db_does_not_conflict(tmp_path):
    """빈 DB에 여러 커넥션이 동시에 붙어도 카탈로그 write-write 충돌이 나면 안 된다.

    GUI는 요청마다 새 커넥션을 열어(api/deps.py::get_db) 최초 진입 시 병렬 요청이
    동시에 스키마를 생성하려 한다 — 이때 DuckDB TransactionException으로 500이 났다.
    """
    import threading

    db_path = tmp_path / "concurrent.duckdb"
    errors: list[Exception] = []
    barrier = threading.Barrier(8)

    def _open() -> None:
        db = Database(path=db_path)
        try:
            barrier.wait(timeout=10)  # 모든 스레드가 동시에 connect하도록 정렬
            db.connect()
            db.close()
        except Exception as e:  # noqa: BLE001 — 실패 사유를 그대로 수집해 단언
            errors.append(e)

    threads = [threading.Thread(target=_open) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == [], f"동시 connect 실패: {errors}"

    verify = Database(path=db_path)
    verify.connect()
    try:
        assert verify._missing_tables() == set()
    finally:
        verify.close()


def test_migration_adds_columns_to_existing_backtest_runs(tmp_path):
    """P1 이전에 만들어진 backtest_runs에도 신규 컬럼이 멱등 적용되어야 한다.

    CREATE TABLE IF NOT EXISTS는 기존 테이블의 컬럼을 늘려주지 않으므로, 이미 P3를
    사용해 테이블이 생성된 DB에서 신규 컬럼 없이 조회하면 깨진다.
    """
    import duckdb

    db_path = tmp_path / "legacy.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """CREATE TABLE backtest_runs (
            run_id VARCHAR NOT NULL, cache_key VARCHAR NOT NULL, strategy_id VARCHAR NOT NULL,
            definition_hash VARCHAR NOT NULL, coverage_fingerprint VARCHAR NOT NULL,
            params JSON NOT NULL, metrics JSON NOT NULL, per_symbol JSON NOT NULL,
            equity_curves JSON NOT NULL, benchmark VARCHAR, benchmark_note VARCHAR,
            errors JSON NOT NULL, executed_at TIMESTAMP NOT NULL, PRIMARY KEY (run_id))"""
    )
    conn.execute(
        "INSERT INTO backtest_runs VALUES ('legacy-run','k','s','d','c',"
        "'{}','{\"total_return\":0.1}','{}','{}',NULL,NULL,'{}',?)",
        [datetime(2026, 7, 20)],
    )
    conn.close()

    db = Database(path=db_path)
    db.connect()
    try:
        assert db._missing_columns() == set()
        record = db.get_backtest_run("legacy-run")
        assert record is not None
        # 마이그레이션 이전 행은 NULL이므로 종목별 모드로 해석된다.
        assert record["is_portfolio"] is False
        assert record["weights"] == {}
    finally:
        db.close()
