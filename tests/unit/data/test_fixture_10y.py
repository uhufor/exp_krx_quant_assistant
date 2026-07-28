"""10년치 실데이터 픽스처(sample_ohlcv_10y.csv)의 무결성과 배선 검증.

이 파일은 pykrx로 한 번 수집해 저장소에 커밋한 **실제 KRX 수정주가**다(합성 데이터가 아님).
재수집으로 재생성하면 값이 달라질 수 있으므로, 회귀를 잡으려면 여기서 형상을 고정한다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.data.fixture_adapter import FIXTURE_10Y_PATH, FixtureAdapter
from quant_krx.data_sources import DATA_SOURCES, OFFLINE_DATA_SOURCES
from quant_krx.workspace.data_loading import _ohlcv_provider_for

SYMBOLS = {"000660", "005930", "006400", "035420", "051910"}
TRADING_DAYS = 2458
OHLC = ["open", "high", "low", "close"]


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return pd.read_csv(FIXTURE_10Y_PATH, dtype={"symbol": str}, parse_dates=["date"])


# --- 파일 형상 ---


def test_file_exists_and_has_expected_shape(df):
    assert set(df["symbol"]) == SYMBOLS
    assert df.groupby("symbol").size().unique().tolist() == [TRADING_DAYS]
    assert len(df) == len(SYMBOLS) * TRADING_DAYS


def test_columns_match_the_1y_fixture(df):
    """두 픽스처가 같은 스키마여야 FixtureAdapter가 분기 없이 읽는다."""
    assert list(df.columns) == ["date", "symbol", "open", "high", "low", "close", "volume"]


def test_covers_a_full_decade(df):
    assert df["date"].min().date() == date(2015, 1, 2)
    assert df["date"].max().date() == date(2024, 12, 30)


# --- 데이터 품질 ---


def test_no_duplicates_or_missing_values(df):
    assert not df.duplicated(["symbol", "date"]).any()
    assert not df.isna().any().any()


def test_all_prices_are_positive(df):
    """액면분할 거래정지일에 pykrx가 open/high/low를 0으로 준다 — 수집 시 O=H=L=C로 보정했다."""
    assert (df[OHLC] > 0).all().all()
    assert (df["volume"] >= 0).all()


def test_ohlc_invariants_hold(df):
    """수정주가 반올림으로 close가 high를 1원 넘는 행이 있었다 — 수집 시 high/low를 넓혔다.

    보정하지 않으면 ATR·볼린저처럼 고저가를 쓰는 팩터가 조용히 오염된다.
    """
    assert (df["high"] == df[OHLC].max(axis=1)).all()
    assert (df["low"] == df[OHLC].min(axis=1)).all()


def test_dates_are_strictly_increasing_per_symbol(df):
    assert (df.groupby("symbol")["date"].diff().dt.days.dropna() > 0).all()


def test_split_adjustment_leaves_no_price_jumps(df):
    """수정주가가 아니면 삼성전자 2018-05 액면분할(50:1)에서 -98% 점프가 남는다."""
    returns = df.groupby("symbol")["close"].pct_change().abs()
    assert (returns.dropna() <= 0.30).all()


def test_contains_multiple_market_regimes(df):
    """확장창/롤링창의 차이는 국면이 바뀌어야 드러난다 — 상승·하락 연도가 모두 있어야 한다."""
    yearly = (
        df[df["symbol"] == "005930"].set_index("date")["close"].resample("YE").last().pct_change()
    ).dropna()
    assert (yearly > 0).any() and (yearly < 0).any()
    assert yearly.min() < -0.20  # 2018·2022·2024 같은 하락 국면


# --- 어댑터 배선 ---


def test_adapter_reads_the_10y_file():
    adapter = FixtureAdapter(fixture_path=FIXTURE_10Y_PATH)
    assert set(adapter.list_symbols()) == SYMBOLS

    data = adapter.fetch_ohlcv("005930", date(2015, 1, 2), date(2024, 12, 30))
    assert len(data.df) == TRADING_DAYS


def test_adapter_slices_by_date_range():
    adapter = FixtureAdapter(fixture_path=FIXTURE_10Y_PATH)
    data = adapter.fetch_ohlcv("005930", date(2020, 1, 1), date(2020, 12, 31))
    assert 200 < len(data.df) < 260  # 1년치 거래일
    assert data.df["date"].min() >= date(2020, 1, 1)


def test_data_source_resolves_to_the_10y_fixture():
    provider = _ohlcv_provider_for("fixture_10y")
    assert isinstance(provider, FixtureAdapter)
    assert len(provider.fetch_ohlcv("005930", date(2015, 1, 2), date(2024, 12, 30)).df) == (
        TRADING_DAYS
    )


def test_default_fixture_is_still_the_1y_file():
    """기존 --data-source fixture 동작이 바뀌면 안 된다(하위호환)."""
    provider = _ohlcv_provider_for("fixture")
    assert len(provider.fetch_ohlcv("005930", date(2015, 1, 2), date(2024, 12, 30)).df) == 252


def test_whitelist_and_offline_set_include_the_new_source():
    """CLI·API·GUI가 모두 이 목록을 보므로, 여기 빠지면 한쪽만 동작하는 드리프트가 생긴다."""
    assert "fixture_10y" in DATA_SOURCES
    assert "fixture_10y" in OFFLINE_DATA_SOURCES
    assert "krx_dart" not in OFFLINE_DATA_SOURCES


def test_offline_sources_never_touch_the_network():
    """fixture_10y가 오프라인 집합에 있어야 펀더멘털도 픽스처 어댑터로 간다 —
    빠지면 KRX 로그인을 시도해 자격증명 없는 환경에서 죽는다(ETF/ETN 필터와 같은 함정)."""
    for source in OFFLINE_DATA_SOURCES:
        assert isinstance(_ohlcv_provider_for(source), FixtureAdapter)
