from __future__ import annotations

from datetime import date
from pathlib import Path

from quant_krx.data.base import DataProvider
from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.data.pykrx_adapter import PyKrxAdapter

FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "sample_ohlcv.csv"


def test_fixture_fetch_market_snapshot_returns_contract_columns():
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    snapshot = adapter.fetch_market_snapshot(date(2024, 1, 2))

    assert set(snapshot.columns) == {"symbol", "close", "volume", "trading_value"}
    assert len(snapshot) == 5
    assert "005930" in snapshot["symbol"].tolist()


def test_fixture_fetch_market_snapshot_trading_value_is_close_times_volume():
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    snapshot = adapter.fetch_market_snapshot(date(2024, 1, 2))

    row = snapshot[snapshot["symbol"] == "005930"].iloc[0]
    assert row["trading_value"] == row["close"] * row["volume"]


def test_fixture_fetch_market_snapshot_is_deterministic():
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    first = adapter.fetch_market_snapshot(date(2024, 1, 2))
    second = adapter.fetch_market_snapshot(date(2024, 1, 2))

    assert first.equals(second)


def test_fixture_fetch_market_snapshot_empty_for_missing_date():
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    snapshot = adapter.fetch_market_snapshot(date(1999, 1, 1))

    assert snapshot.empty
    assert set(snapshot.columns) == {"symbol", "close", "volume", "trading_value"}


def test_pykrx_adapter_satisfies_data_provider_protocol():
    adapter = PyKrxAdapter()
    assert isinstance(adapter, DataProvider)
    assert hasattr(adapter, "fetch_market_snapshot")


def test_pykrx_adapter_fetch_market_snapshot_signature_matches_protocol():
    import inspect

    sig = inspect.signature(PyKrxAdapter.fetch_market_snapshot)
    params = list(sig.parameters)
    assert params == ["self", "date", "market"]
    assert sig.parameters["market"].default == "KRX"
