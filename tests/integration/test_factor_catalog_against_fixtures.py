from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
import pytest

from quant_krx.data.fixture_fundamental import FixtureFundamentalAdapter
from quant_krx.data.loader import load_factor_input
from quant_krx.data.schema import FUNDAMENTAL_SCHEMA_SQL
from quant_krx.factors.base import FactorInput
from quant_krx.factors.dispatch import compute_factor
from quant_krx.factors.registry import list_factors
from quant_krx.storage.schema import SCHEMA_SQL

SYMBOLS = ["000660", "005930", "006400", "035420", "051910"]


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "fixtures.duckdb"
    c = duckdb.connect(str(path))
    c.execute(SCHEMA_SQL)
    c.execute(FUNDAMENTAL_SCHEMA_SQL)

    adapter = FixtureFundamentalAdapter()
    start, end = date(2022, 1, 1), date(2024, 12, 31)

    val = adapter.fetch_valuation(SYMBOLS, start, end)
    val = val.assign(source="fixture", fetched_at=pd.Timestamp.utcnow())
    c.register("_val", val)
    c.execute(
        "INSERT OR REPLACE INTO fundamental_daily "
        "SELECT symbol, date, close, per, pbr, eps, bps, div, dps, market_cap, shares, "
        "source, fetched_at FROM _val"
    )
    c.unregister("_val")

    fin = adapter.fetch_financials(SYMBOLS, start, end)
    fin = fin.assign(source="fixture", fetched_at=pd.Timestamp.utcnow())
    c.register("_fin", fin)
    c.execute("INSERT OR REPLACE INTO financial_statements SELECT * FROM _fin")
    c.unregister("_fin")

    yield c
    c.close()


@pytest.fixture(scope="module")
def ohlcv_by_symbol() -> dict[str, pd.DataFrame]:
    df = pd.read_csv(
        "tests/fixtures/sample_ohlcv.csv", dtype={"symbol": str}, parse_dates=["date"]
    )
    out = {}
    for sym in SYMBOLS:
        sub = df[df["symbol"] == sym].sort_values("date").set_index("date")
        out[sym] = sub[["open", "high", "low", "close", "volume"]].astype(float)
    return out


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_all_32_factors_compute_without_error_on_real_fixture_pipeline(
    conn, ohlcv_by_symbol, symbol
):
    ohlcv = ohlcv_by_symbol[symbol]
    bundle = load_factor_input(conn, symbol, ohlcv=ohlcv)
    fi = FactorInput(ohlcv=bundle.ohlcv, valuation=bundle.valuation, financials=bundle.financials)

    factors = list_factors()
    assert len(factors) == 35

    for meta in factors:
        from quant_krx.factors.registry import get_factor

        factor = get_factor(meta.id)
        result = compute_factor(factor, fi)
        assert set(result.columns) == set(meta.output)
        assert result.index.equals(ohlcv.index)


def test_fundamental_daily_close_matches_ohlcv_close_via_loader(conn, ohlcv_by_symbol):
    for symbol in SYMBOLS:
        ohlcv = ohlcv_by_symbol[symbol]
        bundle = load_factor_input(conn, symbol, ohlcv=ohlcv)
        merged = ohlcv.join(bundle.valuation["close"], rsuffix="_val", how="inner")
        assert (merged["close"] - merged["close_val"]).abs().max() < 1e-6
