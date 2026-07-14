from __future__ import annotations

import pytest

from quant_krx.storage.db import Database


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield db
    db.close()


def test_workspace_tables_exist_and_reconnect_idempotent(tmp_db, tmp_path):
    db2 = Database(path=tmp_path / "test.duckdb")
    db2.connect()
    with db2.cursor() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
    assert {"strategy_activation", "strategy_templates"} <= tables
    db2.close()
