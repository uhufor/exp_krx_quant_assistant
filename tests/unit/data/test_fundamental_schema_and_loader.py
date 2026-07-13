from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
import pytest

from quant_krx.data.fixture_fundamental import FixtureFundamentalAdapter
from quant_krx.data.loader import FundamentalBundle, load_factor_input
from quant_krx.data.schema import FUNDAMENTAL_SCHEMA_SQL
from quant_krx.storage.schema import SCHEMA_SQL


@pytest.fixture
def conn(tmp_path):
    c = duckdb.connect(str(tmp_path / "test.duckdb"))
    c.execute(SCHEMA_SQL)
    c.execute(FUNDAMENTAL_SCHEMA_SQL)
    yield c
    c.close()


def test_ddl_is_idempotent_two_creates(tmp_path):
    c = duckdb.connect(str(tmp_path / "idempotent.duckdb"))
    c.execute(FUNDAMENTAL_SCHEMA_SQL)
    c.execute(FUNDAMENTAL_SCHEMA_SQL)  # 2회 무오류
    tables = {r[0] for r in c.execute("SHOW TABLES").fetchall()}
    assert {"fundamental_daily", "financial_statements"} <= tables
    c.close()


def test_existing_8_tables_untouched_by_fundamental_schema(tmp_path):
    c = duckdb.connect(str(tmp_path / "baseline.duckdb"))
    c.execute(SCHEMA_SQL)
    c.execute(FUNDAMENTAL_SCHEMA_SQL)
    tables = {r[0] for r in c.execute("SHOW TABLES").fetchall()}
    baseline = {
        "symbols", "ohlcv_daily", "data_fetch_runs", "strategy_runs",
        "signals", "reports", "notification_outbox", "run_events",
    }
    assert baseline <= tables
    assert {"fundamental_daily", "financial_statements"} <= tables
    assert len(tables) == 10
    c.close()


def test_fixture_fundamental_adapter_returns_provider_shape():
    adapter = FixtureFundamentalAdapter()
    val = adapter.fetch_valuation(["005930"], date(2024, 1, 1), date(2024, 12, 31))
    assert set(val.columns) == {
        "symbol", "date", "close", "per", "pbr", "eps", "bps", "div", "dps",
        "market_cap", "shares",
    }
    assert (val["symbol"] == "005930").all()
    assert len(val) > 0

    fin = adapter.fetch_financials(["005930"], date(2022, 1, 1), date(2024, 12, 31))
    assert "disclosure_date" in fin.columns
    assert "period_end" in fin.columns
    assert (fin["symbol"] == "005930").all()
    assert len(fin) > 0


def test_fixture_close_matches_ohlcv_close():
    ohlcv = pd.read_csv(
        "tests/fixtures/sample_ohlcv.csv", dtype={"symbol": str}, parse_dates=["date"]
    )
    ohlcv["date"] = ohlcv["date"].dt.date
    adapter = FixtureFundamentalAdapter()
    val = adapter.fetch_valuation(["005930"], date(2024, 1, 1), date(2024, 12, 31))
    merged = ohlcv[ohlcv["symbol"] == "005930"].merge(val, on=["symbol", "date"])
    assert (merged["close_x"] - merged["close_y"]).abs().max() < 1e-9


def test_load_factor_input_round_trip(conn):
    adapter = FixtureFundamentalAdapter()
    val = adapter.fetch_valuation(["005930"], date(2024, 1, 1), date(2024, 12, 31))
    val = val.assign(source="fixture", fetched_at=pd.Timestamp.utcnow())
    conn.register("_val", val)
    conn.execute(
        "INSERT OR REPLACE INTO fundamental_daily "
        "SELECT symbol, date, close, per, pbr, eps, bps, div, dps, market_cap, shares, "
        "source, fetched_at FROM _val"
    )
    conn.unregister("_val")

    fin = adapter.fetch_financials(["005930"], date(2022, 1, 1), date(2024, 12, 31))
    fin = fin.assign(source="fixture", fetched_at=pd.Timestamp.utcnow())
    conn.register("_fin", fin)
    conn.execute("INSERT OR REPLACE INTO financial_statements SELECT * FROM _fin")
    conn.unregister("_fin")

    ohlcv = pd.DataFrame(
        {"close": [70000.0, 71000.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    bundle = load_factor_input(conn, "005930", ohlcv=ohlcv)
    assert isinstance(bundle, FundamentalBundle)
    assert bundle.ohlcv is ohlcv
    assert bundle.valuation is not None
    assert bundle.valuation.index.is_monotonic_increasing
    assert bundle.financials is not None
    assert bundle.financials["disclosure_date"].is_monotonic_increasing


def test_load_factor_input_returns_none_for_missing_symbol(conn):
    ohlcv = pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2024-01-02"]))
    bundle = load_factor_input(conn, "999999", ohlcv=ohlcv)
    assert bundle.valuation is None
    assert bundle.financials is None
