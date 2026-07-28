from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from quant_krx.data.schema import FUNDAMENTAL_SCHEMA_SQL
from quant_krx.data.screening_cache_schema import SCREENING_CACHE_SCHEMA_SQL
from quant_krx.data.screening_schema import SCREENING_SCHEMA_SQL
from quant_krx.formula.definition import Formula
from quant_krx.formula.validation import validate_formula_strict
from quant_krx.rule.definition import Rule
from quant_krx.rule.validation import validate_rule_strict
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.strategy.validation import validate_definition_strict

from .backtest_schema import BACKTEST_MIGRATION_SQL, BACKTEST_SCHEMA_SQL
from .definition_schema import DEFINITION_SCHEMA_SQL
from .schema import SCHEMA_SQL
from .workspace_schema import WORKSPACE_SCHEMA_SQL

_SCHEMA_STATEMENTS = (
    SCHEMA_SQL,
    FUNDAMENTAL_SCHEMA_SQL,
    SCREENING_SCHEMA_SQL,
    SCREENING_CACHE_SCHEMA_SQL,
    DEFINITION_SCHEMA_SQL,
    WORKSPACE_SCHEMA_SQL,
    BACKTEST_SCHEMA_SQL,
)

# DDL에서 테이블명을 추출해 둔다 — 목록을 따로 하드코딩하면 신규 테이블 추가 시 드리프트가 생긴다.
_SCHEMA_TABLES = frozenset(
    re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", "\n".join(_SCHEMA_STATEMENTS))
)

# 이미 존재하는 테이블에 컬럼을 덧붙이는 멱등 마이그레이션. CREATE TABLE IF NOT EXISTS는
# 기존 테이블을 건드리지 않으므로, 신규 컬럼은 반드시 이 경로로 배선해야 한다.
_MIGRATION_STATEMENTS = BACKTEST_MIGRATION_SQL

_MIGRATION_COLUMNS = frozenset(
    re.findall(
        r"ALTER TABLE\s+(\w+)\s+ADD COLUMN IF NOT EXISTS\s+(\w+)",
        "\n".join(_MIGRATION_STATEMENTS),
    )
)

# 같은 프로세스 안에서 DDL 실행을 직렬화한다(아래 _ensure_schema 주석 참고).
_SCHEMA_LOCK = threading.Lock()

# 다른 프로세스가 동시에 같은 테이블을 만드는 경우의 재시도 횟수.
_SCHEMA_MAX_ATTEMPTS = 3


class Database:
    def __init__(self, path: str | Path = "data/quant_krx.duckdb"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        self._conn = duckdb.connect(str(self._path))
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """누락된 테이블이 있을 때만 DDL을 실행한다.

        GUI는 요청마다 새 커넥션을 열므로(`api/deps.py::get_db`) 최초 진입 시 여러 요청이
        동시에 `CREATE TABLE IF NOT EXISTS`를 실행한다. DuckDB에서 두 트랜잭션이 같은
        테이블을 동시에 만들면 카탈로그 write-write 충돌(TransactionException)이 나므로:

        1. 모든 테이블이 이미 있으면 DDL을 아예 실행하지 않는다 — 정상 경로(테이블이 갖춰진
           이후의 거의 모든 호출)에서 쓰기 트랜잭션 자체가 사라진다.
        2. 실제 생성이 필요하면 프로세스 내 락으로 직렬화한다.
        3. 그래도 충돌하면(다른 프로세스가 동시에 생성 중) 재시도한다 — 그 사이 상대가 생성을
           마쳤다면 1번 조건이 성립해 즉시 통과한다.
        """
        assert self._conn is not None
        for attempt in range(_SCHEMA_MAX_ATTEMPTS):
            missing_tables = self._missing_tables()
            missing_columns = self._missing_columns()
            if not missing_tables and not missing_columns:
                return
            try:
                with _SCHEMA_LOCK:
                    if missing_tables:
                        for statement in _SCHEMA_STATEMENTS:
                            self._conn.execute(statement)
                    for statement in _MIGRATION_STATEMENTS:
                        self._conn.execute(statement)
                return
            except duckdb.TransactionException:
                if attempt == _SCHEMA_MAX_ATTEMPTS - 1:
                    raise
                self._conn.rollback()

    def _missing_tables(self) -> set[str]:
        assert self._conn is not None
        existing = {
            row[0]
            for row in self._conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        return set(_SCHEMA_TABLES) - existing

    def _missing_columns(self) -> set[tuple[str, str]]:
        """마이그레이션으로 추가돼야 하는 (테이블, 컬럼) 중 아직 없는 것."""
        assert self._conn is not None
        existing = {
            (row[0], row[1])
            for row in self._conn.execute(
                "SELECT table_name, column_name FROM information_schema.columns"
                " WHERE table_schema='main'"
            ).fetchall()
        }
        return set(_MIGRATION_COLUMNS) - existing

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

    # --- definitions: formula/rule/strategy (PRD-R02 REQ-P2/P3) ---

    def upsert_formula(
        self, formula: Formula, *, now: datetime, check_formula_store: bool = True
    ) -> None:
        resolve_formula = self.get_formula if check_formula_store else None
        validate_formula_strict(formula, resolve_formula=resolve_formula)
        self._upsert_definition("formulas", formula.id, formula.name, formula.version,
                                 formula.schema_version, formula.to_dict(), now)

    def get_formula(self, formula_id: str) -> Formula | None:
        body = self._get_definition("formulas", formula_id)
        return Formula.from_dict(body) if body is not None else None

    def list_formulas(self) -> tuple[Formula, ...]:
        return tuple(Formula.from_dict(body) for body in self._list_definitions("formulas"))

    def delete_formula(self, formula_id: str) -> None:
        self._delete_definition("formulas", formula_id)

    def upsert_rule(self, rule: Rule, *, now: datetime, check_formula_store: bool = True) -> None:
        resolve_formula = self.get_formula if check_formula_store else None
        validate_rule_strict(rule, resolve_formula=resolve_formula)
        self._upsert_definition("rules", rule.id, rule.name, rule.version,
                                 rule.schema_version, rule.to_dict(), now)

    def get_rule(self, rule_id: str) -> Rule | None:
        body = self._get_definition("rules", rule_id)
        return Rule.from_dict(body) if body is not None else None

    def list_rules(self) -> tuple[Rule, ...]:
        return tuple(Rule.from_dict(body) for body in self._list_definitions("rules"))

    def delete_rule(self, rule_id: str) -> None:
        self._delete_definition("rules", rule_id)

    def upsert_strategy(
        self,
        defn: StrategyDefinition,
        *,
        now: datetime,
        check_rule_store: bool = True,
        check_formula_store: bool = True,
    ) -> None:
        resolve_rule = self.get_rule if check_rule_store else None
        resolve_formula = self.get_formula if check_formula_store else None
        validate_definition_strict(defn, resolve_rule=resolve_rule, resolve_formula=resolve_formula)
        self._upsert_definition("strategies", defn.id, defn.name, defn.version,
                                 defn.schema_version, defn.to_dict(), now)

    def get_strategy(self, strategy_id: str) -> StrategyDefinition | None:
        body = self._get_definition("strategies", strategy_id)
        return StrategyDefinition.from_dict(body) if body is not None else None

    def list_strategies(self) -> tuple[StrategyDefinition, ...]:
        return tuple(
            StrategyDefinition.from_dict(body) for body in self._list_definitions("strategies")
        )

    def delete_strategy(self, strategy_id: str) -> None:
        self._delete_definition("strategies", strategy_id)

    def _upsert_definition(
        self,
        table: str,
        id_: str,
        name: str,
        version: str,
        schema_version: int,
        body: dict,
        now: datetime,
    ) -> None:
        with self.cursor() as conn:
            existing = conn.execute(
                f"SELECT created_at FROM {table} WHERE id=?", [id_]
            ).fetchone()
            created_at = existing[0] if existing else now
            conn.execute(
                f"""INSERT OR REPLACE INTO {table}
                        (id, name, version, schema_version, definition, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [id_, name, version, schema_version, json.dumps(body), created_at, now],
            )

    def _get_definition(self, table: str, id_: str) -> dict | None:
        with self.cursor() as conn:
            row = conn.execute(
                f"SELECT definition FROM {table} WHERE id=?", [id_]
            ).fetchone()
        return json.loads(row[0]) if row is not None else None

    def _list_definitions(self, table: str) -> list[dict]:
        with self.cursor() as conn:
            rows = conn.execute(
                f"SELECT definition FROM {table} ORDER BY id"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _delete_definition(self, table: str, id_: str) -> None:
        with self.cursor() as conn:
            conn.execute(f"DELETE FROM {table} WHERE id=?", [id_])

    # --- strategy_activation (PRD-R03 FR-03) ---

    def upsert_activation(self, strategy_id: str, *, active: bool, now: datetime) -> None:
        with self.cursor() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO strategy_activation (strategy_id, active, updated_at)
                   VALUES (?, ?, ?)""",
                [strategy_id, active, now],
            )

    def get_activation(self, strategy_id: str) -> bool:
        """미존재 행 = 비활성(False)."""
        with self.cursor() as conn:
            row = conn.execute(
                "SELECT active FROM strategy_activation WHERE strategy_id=?", [strategy_id]
            ).fetchone()
        return bool(row[0]) if row is not None else False

    def list_active_strategy_ids(self) -> tuple[str, ...]:
        with self.cursor() as conn:
            rows = conn.execute(
                "SELECT strategy_id FROM strategy_activation WHERE active=TRUE ORDER BY strategy_id"
            ).fetchall()
        return tuple(r[0] for r in rows)

    # --- strategy_templates (PRD-R03 FR-21, 사용자 Template만 — Built-in은 코드 상수) ---

    def upsert_template(self, template_id: str, *, name: str, bundle: dict, now: datetime) -> None:
        with self.cursor() as conn:
            existing = conn.execute(
                "SELECT created_at FROM strategy_templates WHERE template_id=?", [template_id]
            ).fetchone()
            created_at = existing[0] if existing else now
            conn.execute(
                """INSERT OR REPLACE INTO strategy_templates
                        (template_id, name, bundle, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)""",
                [template_id, name, json.dumps(bundle), created_at, now],
            )

    def get_template(self, template_id: str) -> dict | None:
        with self.cursor() as conn:
            row = conn.execute(
                "SELECT bundle FROM strategy_templates WHERE template_id=?", [template_id]
            ).fetchone()
        return json.loads(row[0]) if row is not None else None

    def list_templates(self) -> tuple[tuple[str, str], ...]:
        with self.cursor() as conn:
            rows = conn.execute(
                "SELECT template_id, name FROM strategy_templates ORDER BY template_id"
            ).fetchall()
        return tuple((r[0], r[1]) for r in rows)

    def delete_template(self, template_id: str) -> None:
        with self.cursor() as conn:
            conn.execute("DELETE FROM strategy_templates WHERE template_id=?", [template_id])

    # --- screening_conditions (EPIC-03) — body(JSON)가 진실 원천 ---

    def upsert_screening_condition(
        self, id_: str, *, name: str, body: dict, now: datetime
    ) -> None:
        with self.cursor() as conn:
            existing = conn.execute(
                "SELECT created_at FROM screening_conditions WHERE id=?", [id_]
            ).fetchone()
            created_at = existing[0] if existing else now
            conn.execute(
                """INSERT OR REPLACE INTO screening_conditions
                        (id, name, body, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)""",
                [id_, name, json.dumps(body), created_at, now],
            )

    def get_screening_condition(self, id_: str) -> dict | None:
        with self.cursor() as conn:
            row = conn.execute(
                "SELECT body FROM screening_conditions WHERE id=?", [id_]
            ).fetchone()
        return json.loads(row[0]) if row is not None else None

    def list_screening_conditions(self) -> list[dict]:
        with self.cursor() as conn:
            rows = conn.execute(
                "SELECT body FROM screening_conditions ORDER BY id"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def delete_screening_condition(self, id_: str) -> None:
        with self.cursor() as conn:
            conn.execute("DELETE FROM screening_conditions WHERE id=?", [id_])
            # 조건이 사라지면 그 캐시도 의미가 없다(id 재사용 시 오염 방지).
            conn.execute("DELETE FROM screening_result_cache WHERE condition_id=?", [id_])

    # --- 스크리닝 결과 캐시 (P2) ---

    def get_cached_screening_result(
        self, condition_id: str, condition_hash: str, as_of: date
    ) -> list[str] | None:
        with self.cursor() as conn:
            row = conn.execute(
                "SELECT symbols FROM screening_result_cache"
                " WHERE condition_id=? AND condition_hash=? AND as_of=?",
                [condition_id, condition_hash, as_of],
            ).fetchone()
        return json.loads(row[0]) if row is not None else None

    def put_cached_screening_result(
        self,
        condition_id: str,
        condition_hash: str,
        as_of: date,
        symbols: list[str],
        *,
        now: datetime,
    ) -> None:
        with self.cursor() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO screening_result_cache"
                " (condition_id, condition_hash, as_of, symbols, computed_at)"
                " VALUES (?, ?, ?, ?, ?)",
                [condition_id, condition_hash, as_of, json.dumps(symbols), now],
            )

    def clear_screening_cache(self, condition_id: str | None = None) -> int:
        """캐시 삭제. condition_id 생략 시 전체. 삭제된 행 수 반환."""
        with self.cursor() as conn:
            if condition_id is None:
                count = conn.execute(
                    "SELECT count(*) FROM screening_result_cache"
                ).fetchone()[0]
                conn.execute("DELETE FROM screening_result_cache")
            else:
                count = conn.execute(
                    "SELECT count(*) FROM screening_result_cache WHERE condition_id=?",
                    [condition_id],
                ).fetchone()[0]
                conn.execute(
                    "DELETE FROM screening_result_cache WHERE condition_id=?", [condition_id]
                )
        return int(count)

    # --- 백테스트 실행 이력 (P3) ---

    _BACKTEST_COLUMNS = (
        "run_id, cache_key, strategy_id, definition_hash, coverage_fingerprint, "
        "params, metrics, per_symbol, equity_curves, benchmark, benchmark_note, "
        "errors, executed_at, is_portfolio, weights"
    )

    @staticmethod
    def _backtest_row_to_dict(row: tuple) -> dict:
        keys = [c.strip() for c in Database._BACKTEST_COLUMNS.split(",")]
        record = dict(zip(keys, row, strict=True))
        for json_key in ("params", "metrics", "per_symbol", "equity_curves", "errors"):
            record[json_key] = json.loads(record[json_key])
        # 마이그레이션 이전에 기록된 행은 두 컬럼이 NULL이다 — 종목별 모드로 해석한다.
        record["is_portfolio"] = bool(record["is_portfolio"])
        record["weights"] = json.loads(record["weights"]) if record["weights"] else {}
        return record

    def insert_backtest_run(self, record: dict) -> None:
        """실행 이력 1건 삽입. run_id는 호출자가 생성한다(YYYYMMDD-{uuid8} 관례)."""
        with self.cursor() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO backtest_runs ({self._BACKTEST_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    record["run_id"],
                    record["cache_key"],
                    record["strategy_id"],
                    record["definition_hash"],
                    record["coverage_fingerprint"],
                    json.dumps(record["params"]),
                    json.dumps(record["metrics"]),
                    json.dumps(record["per_symbol"]),
                    json.dumps(record["equity_curves"]),
                    record.get("benchmark"),
                    record.get("benchmark_note"),
                    json.dumps(record.get("errors", {})),
                    record["executed_at"],
                    bool(record.get("is_portfolio", False)),
                    json.dumps(record.get("weights", {})),
                ],
            )

    def find_backtest_run_by_cache_key(self, cache_key: str) -> dict | None:
        """동일 cache_key의 가장 최근 실행 1건(캐시 조회용)."""
        with self.cursor() as conn:
            row = conn.execute(
                f"SELECT {self._BACKTEST_COLUMNS} FROM backtest_runs "
                "WHERE cache_key=? ORDER BY executed_at DESC LIMIT 1",
                [cache_key],
            ).fetchone()
        return self._backtest_row_to_dict(row) if row is not None else None

    def get_backtest_run(self, run_id: str) -> dict | None:
        with self.cursor() as conn:
            row = conn.execute(
                f"SELECT {self._BACKTEST_COLUMNS} FROM backtest_runs WHERE run_id=?", [run_id]
            ).fetchone()
        return self._backtest_row_to_dict(row) if row is not None else None

    def list_backtest_runs(self, *, strategy_id: str | None = None, limit: int = 50) -> list[dict]:
        """최근 실행 순 목록. strategy_id 지정 시 해당 전략만."""
        where = "WHERE strategy_id=?" if strategy_id else ""
        params = [strategy_id, limit] if strategy_id else [limit]
        with self.cursor() as conn:
            rows = conn.execute(
                f"SELECT {self._BACKTEST_COLUMNS} FROM backtest_runs {where} "
                "ORDER BY executed_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._backtest_row_to_dict(row) for row in rows]

    def delete_backtest_run(self, run_id: str) -> None:
        with self.cursor() as conn:
            conn.execute("DELETE FROM backtest_runs WHERE run_id=?", [run_id])
