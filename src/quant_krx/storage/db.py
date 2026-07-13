from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from quant_krx.data.schema import FUNDAMENTAL_SCHEMA_SQL

from .schema import SCHEMA_SQL


class Database:
    def __init__(self, path: str | Path = "data/quant_krx.duckdb"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        self._conn = duckdb.connect(str(self._path))
        self._conn.execute(SCHEMA_SQL)
        self._conn.execute(FUNDAMENTAL_SCHEMA_SQL)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def cursor(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        yield self._conn

    # --- OHLCV ---

    def upsert_ohlcv(self, symbol: str, df: pd.DataFrame, source: str, fetched_at: datetime) -> int:
        """OHLCV DataFrame을 upsert. 삽입/갱신된 행 수 반환."""
        if df.empty:
            return 0
        tmp = df.copy()
        tmp["symbol"] = symbol
        tmp["source"] = source
        tmp["fetched_at"] = fetched_at
        with self.cursor() as conn:
            conn.register("_tmp_df", tmp)
            conn.execute("""
                INSERT OR REPLACE INTO ohlcv_daily
                    (symbol, date, open, high, low, close, volume, source, fetched_at)
                SELECT symbol, date, open, high, low, close, volume, source, fetched_at
                FROM _tmp_df
            """)
            conn.unregister("_tmp_df")
        return len(tmp)

    def fetch_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        with self.cursor() as conn:
            return conn.execute(
                "SELECT * FROM ohlcv_daily WHERE symbol=? AND date>=? AND date<=? ORDER BY date",
                [symbol, start, end],
            ).df()

    # --- signals / reports ---

    def insert_signal(self, signal: dict) -> None:
        """신호를 signals 테이블에 저장. 중복 id는 무시."""
        with self.cursor() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO signals"
                " (id, run_id, symbol, signal_date, signal_type,"
                " strategy, score, metrics, risk_flags)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    signal["id"],
                    signal["run_id"],
                    signal["symbol"],
                    signal["signal_date"],
                    signal["signal_type"],
                    signal.get("strategy_name", signal.get("strategy", "")),
                    signal["score"],
                    json.dumps(signal.get("metrics", {})),
                    json.dumps(signal.get("risk_flags", [])),
                ],
            )

    def insert_report(
        self, signal_id: str, report_type: str, content: str, run_id: str
    ) -> None:
        """리포트를 reports 테이블에 저장."""
        with self.cursor() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO reports (id, run_id, signal_id, report_type, content)
                   VALUES (?, ?, ?, ?, ?)""",
                [str(uuid.uuid4()), run_id, signal_id, report_type, content],
            )

    # --- notification_outbox ---

    def enqueue_notification(
        self, run_id: str, channel: str, content_hash: str, payload: str
    ) -> str:
        """알림을 outbox에 추가. 중복(channel+content_hash) 시 기존 id 반환."""
        nid = str(uuid.uuid4())
        with self.cursor() as conn:
            try:
                conn.execute(
                    """INSERT INTO notification_outbox (id, run_id, channel, content_hash, payload)
                       VALUES (?, ?, ?, ?, ?)""",
                    [nid, run_id, channel, content_hash, payload],
                )
            except duckdb.ConstraintException:
                row = conn.execute(
                    "SELECT id FROM notification_outbox WHERE channel=? AND content_hash=?",
                    [channel, content_hash],
                ).fetchone()
                return row[0] if row else nid
        return nid

    def get_notification_status(self, notification_id: str) -> str:
        """notification_outbox 행의 status 반환. 없으면 'unknown'."""
        with self.cursor() as conn:
            row = conn.execute(
                "SELECT status FROM notification_outbox WHERE id=?",
                [notification_id],
            ).fetchone()
            return row[0] if row else "unknown"

    def mark_notification_sent(self, notification_id: str) -> None:
        with self.cursor() as conn:
            conn.execute(
                "UPDATE notification_outbox SET status='sent', sent_at=? WHERE id=?",
                [datetime.utcnow(), notification_id],
            )

    def mark_notification_failed(self, notification_id: str, error: str) -> None:
        with self.cursor() as conn:
            conn.execute(
                """UPDATE notification_outbox
                   SET status='failed', error_msg=?, retry_count=retry_count+1
                   WHERE id=?""",
                [error, notification_id],
            )

    def get_pending_notifications(self, channel: str | None = None) -> pd.DataFrame:
        with self.cursor() as conn:
            if channel:
                return conn.execute(
                    "SELECT * FROM notification_outbox"
                    " WHERE status='pending' AND channel=? ORDER BY created_at",
                    [channel],
                ).df()
            return conn.execute(
                "SELECT * FROM notification_outbox WHERE status='pending' ORDER BY created_at"
            ).df()

    # --- run_events ---

    def log_event(self, run_id: str, event_type: str, message: str, level: str = "INFO") -> None:
        with self.cursor() as conn:
            conn.execute(
                """INSERT INTO run_events (id, run_id, event_type, message, level)
                   VALUES (nextval('run_events_id_seq'), ?, ?, ?, ?)""",
                [run_id, event_type, message, level],
            )
