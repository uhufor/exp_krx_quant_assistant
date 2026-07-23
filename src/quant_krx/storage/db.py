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
from quant_krx.data.screening_schema import SCREENING_SCHEMA_SQL
from quant_krx.formula.definition import Formula
from quant_krx.formula.validation import validate_formula_strict
from quant_krx.rule.definition import Rule
from quant_krx.rule.validation import validate_rule_strict
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.strategy.validation import validate_definition_strict

from .definition_schema import DEFINITION_SCHEMA_SQL
from .schema import SCHEMA_SQL
from .workspace_schema import WORKSPACE_SCHEMA_SQL


class Database:
    def __init__(self, path: str | Path = "data/quant_krx.duckdb"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        self._conn = duckdb.connect(str(self._path))
        self._conn.execute(SCHEMA_SQL)
        self._conn.execute(FUNDAMENTAL_SCHEMA_SQL)
        self._conn.execute(SCREENING_SCHEMA_SQL)
        self._conn.execute(DEFINITION_SCHEMA_SQL)
        self._conn.execute(WORKSPACE_SCHEMA_SQL)

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
