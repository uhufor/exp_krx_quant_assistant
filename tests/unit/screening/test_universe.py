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


class _SpecialSymbolAdapter(_NamedFixtureAdapter):
    """ETF/ETN 목록을 주입할 수 있는 테스트 어댑터.

    예전에는 pykrx 모듈을 monkeypatch했으나, ETF/ETN 조회가 provider 프로토콜로 올라가면서
    provider를 갈아끼우는 방식으로 바뀌었다(이게 실제 호출 경로와 같다).
    """

    def __init__(self, *, etf=(), etn=(), **kwargs):
        super().__init__(**kwargs)
        self._etf = set(etf)
        self._etn = set(etn)
        self.etf_calls: list[object] = []
        self.etn_calls: list[object] = []

    def list_etf_symbols(self, as_of=None):
        self.etf_calls.append(as_of)
        return set(self._etf)

    def list_etn_symbols(self, as_of=None):
        self.etn_calls.append(as_of)
        return set(self._etn)


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


def test_etf_filter_excludes_etf_symbols():
    adapter = _SpecialSymbolAdapter(etf=["005930"], fixture_path=FIXTURE_PATH)
    result = resolve_scan_universe(adapter, frozenset({"etf"}))
    assert set(result) == set(ALL_SYMBOLS) - {"005930"}


def test_etn_filter_excludes_etn_symbols():
    adapter = _SpecialSymbolAdapter(etn=["000660"], fixture_path=FIXTURE_PATH)
    result = resolve_scan_universe(adapter, frozenset({"etn"}))
    assert set(result) == set(ALL_SYMBOLS) - {"000660"}


def test_etf_and_etn_filters_combine():
    adapter = _SpecialSymbolAdapter(
        etf=["005930"], etn=["000660"], fixture_path=FIXTURE_PATH
    )
    result = resolve_scan_universe(adapter, frozenset({"etf", "etn"}))
    assert set(result) == set(ALL_SYMBOLS) - {"005930", "000660"}


def test_etf_etn_lookup_is_skipped_when_filter_absent():
    """필터가 없으면 조회 자체를 하지 않는다(불필요한 네트워크 호출 방지)."""
    adapter = _SpecialSymbolAdapter(etf=["005930"], fixture_path=FIXTURE_PATH)
    resolve_scan_universe(adapter, frozenset())
    assert adapter.etf_calls == []
    assert adapter.etn_calls == []


def test_etf_etn_lookup_receives_as_of():
    """제외 목록도 상장 목록과 같은 시점 기준이어야 한다."""
    from datetime import date

    adapter = _SpecialSymbolAdapter(etf=["005930"], etn=[], fixture_path=FIXTURE_PATH)
    resolve_scan_universe(adapter, frozenset({"etf", "etn"}), as_of=date(2020, 3, 2))

    assert adapter.etf_calls == [date(2020, 3, 2)]
    assert adapter.etn_calls == [date(2020, 3, 2)]


def test_etf_filter_does_not_import_pykrx():
    """fixture 데이터소스로 오프라인 실행할 때 ETF 필터가 pykrx를 끌어오면 안 된다.

    예전에는 universe가 pykrx를 직접 호출해, --data-source fixture로 돌려도 KRX 로그인을
    시도하고 자격증명이 없으면 IndexError로 스크리닝이 죽었다.
    """
    import subprocess
    import sys

    code = (
        "import sys;"
        "from quant_krx.data.fixture_adapter import FixtureAdapter;"
        "from quant_krx.screening.universe import resolve_scan_universe;"
        f"resolve_scan_universe(FixtureAdapter(fixture_path=r'{FIXTURE_PATH}'),"
        " frozenset({'etf','etn'}));"
        "print('pykrx' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False", f"pykrx가 로드되었다: {out.stdout} {out.stderr}"


def test_provider_lookup_failure_does_not_kill_screening(provider, monkeypatch):
    """제외 목록 조회가 실패해도 스크리닝 전체가 죽지 않는다(제외가 덜 적용될 뿐)."""

    class _FailingAdapter(_NamedFixtureAdapter):
        def list_etf_symbols(self, as_of=None):
            return set()  # PyKrxAdapter가 내부에서 예외를 흡수해 빈 집합을 준다

    result = resolve_scan_universe(
        _FailingAdapter(fixture_path=FIXTURE_PATH), frozenset({"etf"})
    )
    assert set(result) == set(ALL_SYMBOLS)


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
        def list_symbols(self, market="KRX", as_of=None):
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


def test_as_of_is_passed_through_to_provider():
    """과거 구간 스크리닝은 그 시점 상장 종목을 조회해야 한다(생존 편향 방지, P2).

    as_of가 provider까지 전달되지 않으면 2020년 백테스트가 2026년 상장 종목만 후보로
    삼게 되어, 그 사이 상장폐지된 종목이 통째로 빠지고 성과가 부풀려진다.
    """
    from datetime import date

    seen: list[date | None] = []

    class _RecordingProvider(_NamedFixtureAdapter):
        def list_symbols(self, market="KRX", as_of=None):
            seen.append(as_of)
            return ["005930", "000660"]

    provider = _RecordingProvider(fixture_path=FIXTURE_PATH)
    resolve_scan_universe(provider, frozenset(), as_of=date(2020, 3, 2))

    assert seen == [date(2020, 3, 2)]


def test_as_of_omitted_defaults_to_none():
    """as_of 미지정 시 provider가 현재 기준으로 판단하도록 None을 그대로 넘긴다."""
    seen: list[object] = []

    class _RecordingProvider(_NamedFixtureAdapter):
        def list_symbols(self, market="KRX", as_of=None):
            seen.append(as_of)
            return ["005930"]

    resolve_scan_universe(_RecordingProvider(fixture_path=FIXTURE_PATH), frozenset())
    assert seen == [None]
