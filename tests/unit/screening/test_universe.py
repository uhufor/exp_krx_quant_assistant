from __future__ import annotations

from pathlib import Path

import pytest

from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.screening.errors import EmptyUniverseError, UnsupportedFilterError
from quant_krx.screening.universe import (
    _is_preferred_stock,
    _is_spac,
    resolve_scan_universe,
)

FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "sample_ohlcv.csv"
ALL_SYMBOLS = ["000660", "005930", "006400", "035420", "051910"]

_NAMES = {
    "000660": "SK하이닉스",
    "005930": "삼성전자",
    "006400": "삼성SDI우",
    "035420": "NAVER",
    "051910": "한화플러스제1호기업인수목적",
}


class _NamedFixtureAdapter(FixtureAdapter):
    """FixtureAdapter를 그대로 쓰되 fetch_metadata만 종목명을 채워 반환하는 테스트 전용 어댑터.

    실제 FixtureAdapter.fetch_metadata는 name 필드를 채우지 않으므로(테스트/오프라인 목적),
    우선주/SPAC 명칭 기반 필터를 검증하려면 이 서브클래스로 name만 보강한다.
    """

    def fetch_metadata(self, symbols):
        return {s: {"symbol": s, "name": _NAMES.get(s, "")} for s in symbols}


class _StubStock:
    """pykrx.stock 모듈을 대체하는 최소 스텁 — etf/etn 티커 목록만 제공."""

    def __init__(self, etf=(), etn=()):
        self._etf = list(etf)
        self._etn = list(etn)

    def get_etf_ticker_list(self):
        return self._etf

    def get_etn_ticker_list(self):
        return self._etn


@pytest.fixture
def provider():
    return _NamedFixtureAdapter(fixture_path=FIXTURE_PATH)


# --- 순수 함수 단위 테스트(_is_preferred_stock / _is_spac) -------------------


@pytest.mark.parametrize(
    "name",
    ["삼성전자우", "삼성전자우B", "LG생활건강우", "현대차2우B", "삼성전기1우", "OO우선주"],
)
def test_is_preferred_stock_true_cases(name):
    assert _is_preferred_stock(name) is True


@pytest.mark.parametrize("name", ["삼성전자", "SK하이닉스", "NAVER", "카카오"])
def test_is_preferred_stock_false_cases(name):
    assert _is_preferred_stock(name) is False


def test_is_spac_true():
    assert _is_spac("한화플러스제1호기업인수목적") is True


def test_is_spac_false():
    assert _is_spac("삼성전자") is False


# --- resolve_scan_universe: 필터 없음 ---------------------------------------


def test_no_filters_returns_all_symbols_sorted(provider):
    result = resolve_scan_universe(provider, frozenset())
    assert result == sorted(ALL_SYMBOLS)


# --- etf / etn 필터 -----------------------------------------------------------


def test_etf_filter_excludes_etf_symbols(provider, monkeypatch):
    monkeypatch.setattr(
        "quant_krx.screening.universe._krx_stock",
        lambda: _StubStock(etf=["005930"]),
    )
    result = resolve_scan_universe(provider, frozenset({"etf"}))
    assert set(result) == set(ALL_SYMBOLS) - {"005930"}


def test_etn_filter_excludes_etn_symbols(provider, monkeypatch):
    monkeypatch.setattr(
        "quant_krx.screening.universe._krx_stock",
        lambda: _StubStock(etn=["000660"]),
    )
    result = resolve_scan_universe(provider, frozenset({"etn"}))
    assert set(result) == set(ALL_SYMBOLS) - {"000660"}


def test_etf_and_etn_filters_combine(provider, monkeypatch):
    monkeypatch.setattr(
        "quant_krx.screening.universe._krx_stock",
        lambda: _StubStock(etf=["005930"], etn=["000660"]),
    )
    result = resolve_scan_universe(provider, frozenset({"etf", "etn"}))
    assert set(result) == set(ALL_SYMBOLS) - {"005930", "000660"}


# --- preferred / spac 필터 ------------------------------------------------


def test_preferred_filter_excludes_preferred_named_symbols(provider):
    result = resolve_scan_universe(provider, frozenset({"preferred"}))
    assert set(result) == set(ALL_SYMBOLS) - {"006400"}


def test_spac_filter_excludes_spac_named_symbols(provider):
    result = resolve_scan_universe(provider, frozenset({"spac"}))
    assert set(result) == set(ALL_SYMBOLS) - {"051910"}


def test_preferred_and_spac_filters_combine(provider):
    result = resolve_scan_universe(provider, frozenset({"preferred", "spac"}))
    assert set(result) == set(ALL_SYMBOLS) - {"006400", "051910"}


# --- 빈 유니버스 ---------------------------------------------------------------


def test_empty_universe_raises_when_all_symbols_filtered_out():
    class _AllPreferredAdapter(_NamedFixtureAdapter):
        def fetch_metadata(self, symbols):
            return {s: {"symbol": s, "name": "전종목우"} for s in symbols}

    with pytest.raises(EmptyUniverseError):
        resolve_scan_universe(
            _AllPreferredAdapter(fixture_path=FIXTURE_PATH), frozenset({"preferred"})
        )


def test_empty_universe_raises_when_provider_returns_no_symbols():
    class _EmptyProvider(_NamedFixtureAdapter):
        def list_symbols(self, market="KRX"):
            return []

    with pytest.raises(EmptyUniverseError):
        resolve_scan_universe(_EmptyProvider(fixture_path=FIXTURE_PATH), frozenset())


# --- 미지원 제외 필터 6종 -----------------------------------------------------


@pytest.mark.parametrize(
    "flt",
    [
        "administrative_issue",
        "investment_alert",
        "trading_halt",
        "liquidation_trading",
        "market_alert",
        "unfaithful_disclosure",
    ],
)
def test_unsupported_filter_raises(provider, flt):
    with pytest.raises(UnsupportedFilterError):
        resolve_scan_universe(provider, frozenset({flt}))
