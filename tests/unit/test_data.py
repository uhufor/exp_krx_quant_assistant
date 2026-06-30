import pytest
from datetime import date
from pathlib import Path
from quant_krx.data import OHLCVData, ProviderMeta
from quant_krx.data.fixture_adapter import FixtureAdapter

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_ohlcv.csv"


@pytest.fixture
def adapter():
    return FixtureAdapter(fixture_path=FIXTURE_PATH)


def test_fixture_list_symbols(adapter):
    symbols = adapter.list_symbols()
    assert len(symbols) == 5
    assert "005930" in symbols


def test_fixture_fetch_ohlcv_shape(adapter):
    result = adapter.fetch_ohlcv("005930", date(2024, 1, 2), date(2024, 12, 31))
    assert isinstance(result, OHLCVData)
    assert not result.df.empty
    assert set(result.df.columns) >= {"date", "open", "high", "low", "close", "volume"}


def test_fixture_fetch_ohlcv_no_negative_price(adapter):
    result = adapter.fetch_ohlcv("005930", date(2024, 1, 2), date(2024, 12, 31))
    assert (result.df["close"] > 0).all()


def test_fixture_ohlcv_validate_ok(adapter):
    result = adapter.fetch_ohlcv("005930", date(2024, 1, 2), date(2024, 12, 31))
    issues = result.validate()
    assert issues == []


def test_fixture_ohlcv_validate_missing_column():
    import pandas as pd
    from datetime import datetime
    bad_df = pd.DataFrame({"date": [date(2024, 1, 2)], "close": [50000.0]})  # open/high/low/volume 없음
    data = OHLCVData(
        symbol="TEST",
        df=bad_df,
        meta=ProviderMeta(source_name="test", fetched_at=datetime.utcnow()),
    )
    issues = data.validate()
    assert any("Missing columns" in i for i in issues)


def test_fixture_fetch_benchmark(adapter):
    result = adapter.fetch_benchmark("KOSPI", date(2024, 1, 2), date(2024, 12, 31))
    assert isinstance(result, OHLCVData)
    assert not result.df.empty


def test_fixture_fetch_metadata(adapter):
    meta = adapter.fetch_metadata(["005930", "000660"])
    assert "005930" in meta
    assert meta["005930"]["source"] == "Fixture"


def test_data_provider_protocol():
    from quant_krx.data.base import DataProvider
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    assert isinstance(adapter, DataProvider)
