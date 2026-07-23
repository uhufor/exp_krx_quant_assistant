from __future__ import annotations

import socket
import time
from datetime import date, datetime

import pandas as pd
import pytest

from quant_krx.data.base import OHLCVData, ProviderMeta
from quant_krx.screening.universe_data import _gap_ranges, fetch_universe_ohlcv_cached
from quant_krx.storage.db import Database


class _RecordingOhlcvProvider:
    """호출 인자를 기록하는 스텁 provider — 증분 fetch 범위(캐시 히트/미스) 검증용."""

    source_name = "Stub"

    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date]] = []

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        self.calls.append((symbol, start, end))
        dates = pd.date_range(start, end, freq="D")
        df = pd.DataFrame(
            {
                "date": [d.date() for d in dates],
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000,
            }
        )
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        return OHLCVData(symbol=symbol, df=df, meta=meta)


class _BulkByDateProvider:
    """fetch_ohlcv_bulk_by_date/list_trading_days를 지원하는 스텁(PyKrxAdapter 흉내).

    날짜별 벌크 조회 경로가 실제로 선택되는지(종목별 fetch_ohlcv 호출이 없는지),
    거래일 수만큼만 호출되는지 검증하는 데 쓴다.
    """

    source_name = "StubBulk"

    def __init__(self, symbols: list[str], trading_days: list[date],
                 failing_days: set[date] | None = None) -> None:
        self._symbols = symbols
        self._trading_days = trading_days
        self._failing_days = failing_days or set()
        self.bulk_calls: list[date] = []

    def list_trading_days(self, start: date, end: date) -> list[date]:
        return [d for d in self._trading_days if start <= d <= end]

    def fetch_ohlcv_bulk_by_date(self, d: date, market: str = "KRX") -> pd.DataFrame:
        self.bulk_calls.append(d)
        if d in self._failing_days:
            raise RuntimeError(f"{d} 벌크 조회 실패(가정)")
        return pd.DataFrame(
            {
                "symbol": self._symbols,
                "date": [d] * len(self._symbols),
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000,
            }
        )

    # fetch_ohlcv는 의도적으로 정의하지 않는다 — 벌크 경로가 실제로 쓰이는지
    # (이게 호출되면 안 됨을) 증명하기 위함.


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "test.duckdb")
    database.connect()
    yield database
    database.close()


class TestGapRanges:
    def test_no_existing_data_returns_full_range(self):
        assert _gap_ranges(None, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 10))
        ]

    def test_fully_covered_returns_no_gaps(self):
        existing = (date(2026, 1, 1), date(2026, 1, 10))
        assert _gap_ranges(existing, date(2026, 1, 3), date(2026, 1, 8)) == []

    def test_both_gaps(self):
        existing = (date(2026, 1, 5), date(2026, 1, 6))
        assert _gap_ranges(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 4)),
            (date(2026, 1, 7), date(2026, 1, 10)),
        ]


class TestFetchUniverseOhlcvCached:
    def test_first_call_fetches_full_range(self, db):
        provider = _RecordingOhlcvProvider()
        result = fetch_universe_ohlcv_cached(
            db, provider, ["005930"], start=date(2026, 1, 1), end=date(2026, 1, 10)
        )
        assert provider.calls == [("005930", date(2026, 1, 1), date(2026, 1, 10))]
        assert len(result["005930"]) == 10

    def test_second_call_same_range_is_cache_hit_skips_provider(self, db):
        provider = _RecordingOhlcvProvider()
        for _ in range(2):
            fetch_universe_ohlcv_cached(
                db, provider, ["005930"], start=date(2026, 1, 1), end=date(2026, 1, 10)
            )
        assert len(provider.calls) == 1  # 두 번째 호출은 이미 커버되어 provider 호출 0회

    def test_extended_end_date_fetches_only_tail_gap(self, db):
        provider = _RecordingOhlcvProvider()
        fetch_universe_ohlcv_cached(
            db, provider, ["005930"], start=date(2026, 1, 1), end=date(2026, 1, 10)
        )
        result = fetch_universe_ohlcv_cached(
            db, provider, ["005930"], start=date(2026, 1, 1), end=date(2026, 1, 15)
        )
        assert provider.calls == [
            ("005930", date(2026, 1, 1), date(2026, 1, 10)),
            ("005930", date(2026, 1, 11), date(2026, 1, 15)),
        ]
        assert len(result["005930"]) == 15

    def test_use_cache_false_always_refetches_full_range(self, db):
        provider = _RecordingOhlcvProvider()
        for _ in range(2):
            fetch_universe_ohlcv_cached(
                db,
                provider,
                ["005930"],
                start=date(2026, 1, 1),
                end=date(2026, 1, 10),
                use_cache=False,
            )
        assert provider.calls == [
            ("005930", date(2026, 1, 1), date(2026, 1, 10)),
            ("005930", date(2026, 1, 1), date(2026, 1, 10)),
        ]

    def test_multiple_symbols_each_get_own_gap_tracking(self, db):
        provider = _RecordingOhlcvProvider()
        result = fetch_universe_ohlcv_cached(
            db,
            provider,
            ["005930", "000660"],
            start=date(2026, 1, 1),
            end=date(2026, 1, 5),
        )
        assert set(provider.calls) == {
            ("005930", date(2026, 1, 1), date(2026, 1, 5)),
            ("000660", date(2026, 1, 1), date(2026, 1, 5)),
        }
        assert set(result) == {"005930", "000660"}
        assert len(result["005930"]) == 5
        assert len(result["000660"]) == 5


class _SlowOhlcvProvider:
    """종목당 고정 지연을 흉내내는 스텁 — 병렬 fetch로 총 소요시간이 줄어드는지 검증용."""

    source_name = "Stub"
    DELAY_SECONDS = 0.05

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        time.sleep(self.DELAY_SECONDS)
        dates = pd.date_range(start, end, freq="D")
        df = pd.DataFrame(
            {
                "date": [d.date() for d in dates],
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000,
            }
        )
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        return OHLCVData(symbol=symbol, df=df, meta=meta)


class _PartiallyFailingOhlcvProvider:
    """지정된 종목에서만 예외를 던지는 스텁 — 종목 단위 실패 격리 검증용."""

    source_name = "Stub"

    def __init__(self, failing_symbols: set[str]) -> None:
        self.failing_symbols = failing_symbols
        self.calls: list[str] = []

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        self.calls.append(symbol)
        if symbol in self.failing_symbols:
            raise RuntimeError(f"{symbol} 조회 실패(상장폐지 가정)")
        dates = pd.date_range(start, end, freq="D")
        df = pd.DataFrame(
            {
                "date": [d.date() for d in dates],
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000,
            }
        )
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        return OHLCVData(symbol=symbol, df=df, meta=meta)


class TestParallelFetchPerformance:
    def test_many_symbols_fetched_faster_than_sequential_would_take(self, db):
        symbols = [f"{i:06d}" for i in range(40)]
        provider = _SlowOhlcvProvider()

        started = time.monotonic()
        result = fetch_universe_ohlcv_cached(
            db, provider, symbols, start=date(2026, 1, 1), end=date(2026, 1, 3)
        )
        elapsed = time.monotonic() - started

        sequential_worst_case = len(symbols) * provider.DELAY_SECONDS
        assert elapsed < sequential_worst_case / 2  # 병렬화로 절반 미만 시간에 완료
        assert set(result) == set(symbols)


class _SocketTimeoutRecordingProvider:
    """fetch 도중 socket 기본 타임아웃이 실제로 설정돼 있는지 기록하는 스텁."""

    source_name = "Stub"

    def __init__(self) -> None:
        self.observed_timeouts: list[float | None] = []

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        self.observed_timeouts.append(socket.getdefaulttimeout())
        dates = pd.date_range(start, end, freq="D")
        df = pd.DataFrame(
            {
                "date": [d.date() for d in dates],
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000,
            }
        )
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        return OHLCVData(symbol=symbol, df=df, meta=meta)


class _HangingThenNormalProvider:
    """일부 종목에서 '연결은 됐지만 응답이 없는' 서버를 흉내내는 스텁(실제 Naver
    스로틀링 상황과 동일한 형태 — connect 자체는 성공하고 recv()에서 블록됨).

    로컬 TCP 서버 소켓을 열어 accept는 하되 아무 데이터도 보내지 않는다. socket 기본
    타임아웃이 설정돼 있지 않으면 recv()가 영원히 블록되므로, 이 스텁을 쓰는 테스트가
    빠르게 끝난다는 사실 자체가 타임아웃 설정이 실제로 동작함을 증명한다.
    """

    source_name = "Stub"

    def __init__(self, hanging_symbols: set[str]) -> None:
        self.hanging_symbols = hanging_symbols
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(1)
        self.port = self._server.getsockname()[1]

    def close(self) -> None:
        self._server.close()

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        if symbol in self.hanging_symbols:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.connect(("127.0.0.1", self.port))
                client.recv(1024)  # 서버가 절대 응답하지 않음 — 타임아웃 없이는 영원히 블록
            raise AssertionError("recv()가 실제로 데이터를 받아버림 — 테스트 가정 위반")
        dates = pd.date_range(start, end, freq="D")
        df = pd.DataFrame(
            {
                "date": [d.date() for d in dates],
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000,
            }
        )
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        return OHLCVData(symbol=symbol, df=df, meta=meta)


class TestSocketTimeoutIsolation:
    def test_default_timeout_is_none_before_and_after_call(self, db):
        assert socket.getdefaulttimeout() is None
        provider = _SocketTimeoutRecordingProvider()
        fetch_universe_ohlcv_cached(
            db, provider, ["005930"], start=date(2026, 1, 1), end=date(2026, 1, 2)
        )
        assert socket.getdefaulttimeout() is None  # 호출 후 원래 상태로 복원됨

    def test_socket_timeout_is_set_during_fetch_window(self, db):
        provider = _SocketTimeoutRecordingProvider()
        fetch_universe_ohlcv_cached(
            db, provider, ["005930", "000660"], start=date(2026, 1, 1), end=date(2026, 1, 2)
        )
        assert all(t == pytest.approx(30.0) for t in provider.observed_timeouts)

    def test_unresponsive_connection_times_out_instead_of_hanging_forever(
        self, db, monkeypatch
    ):
        """응답 없는 종목이 있어도 socket 타임아웃 덕분에 전체 호출이 끝난다(회귀 방지:
        타임아웃 미설정 시 이 테스트는 무한정 멈춰서 CI가 강제 종료될 때까지 걸린다)."""
        import quant_krx.screening.universe_data as universe_data_mod

        monkeypatch.setattr(universe_data_mod, "_SOCKET_TIMEOUT_SECONDS", 1.0)

        provider = _HangingThenNormalProvider(hanging_symbols={"999999"})
        try:
            started = time.monotonic()
            result = fetch_universe_ohlcv_cached(
                db, provider, ["005930", "999999"], start=date(2026, 1, 1), end=date(2026, 1, 2)
            )
            elapsed = time.monotonic() - started
        finally:
            provider.close()

        assert elapsed < 5.0  # 1초 타임아웃 기준 여유 있게 검증(무한 대기였다면 실패)
        assert len(result["005930"]) == 2
        assert result["999999"].empty  # 타임아웃으로 실패 처리되어 격리됨


class TestProgressLogging:
    def test_logs_info_per_symbol_with_progress_and_timing(self, db, caplog):
        provider = _RecordingOhlcvProvider()
        with caplog.at_level("INFO", logger="quant_krx.screening.universe_data"):
            fetch_universe_ohlcv_cached(
                db, provider, ["005930", "000660"], start=date(2026, 1, 1), end=date(2026, 1, 3)
            )

        messages = [r.getMessage() for r in caplog.records]
        assert any("[1/2]" in m for m in messages)
        assert any("[2/2]" in m for m in messages)
        assert any("005930" in m and "평균" in m for m in messages)
        assert any("OHLCV 확보 완료" in m for m in messages)


class TestSymbolLevelFailureIsolation:
    def test_one_symbol_failure_does_not_block_others(self, db):
        provider = _PartiallyFailingOhlcvProvider(failing_symbols={"000002"})
        symbols = ["000001", "000002", "000003"]

        result = fetch_universe_ohlcv_cached(
            db, provider, symbols, start=date(2026, 1, 1), end=date(2026, 1, 3)
        )

        assert len(result["000001"]) == 3
        assert len(result["000003"]) == 3
        assert result["000002"].empty  # 실패 종목은 빈 결과, 예외가 전체를 막지 않음

    def test_on_symbol_error_callback_invoked_with_failing_symbol(self, db):
        provider = _PartiallyFailingOhlcvProvider(failing_symbols={"000002"})
        errors: list[tuple[str, Exception]] = []

        fetch_universe_ohlcv_cached(
            db,
            provider,
            ["000001", "000002"],
            start=date(2026, 1, 1),
            end=date(2026, 1, 3),
            on_symbol_error=lambda symbol, exc: errors.append((symbol, exc)),
        )

        assert len(errors) == 1
        assert errors[0][0] == "000002"
        assert isinstance(errors[0][1], RuntimeError)


class TestBulkByDateFetchPath:
    def test_uses_bulk_path_when_provider_supports_it(self, db):
        symbols = ["005930", "000660", "006400"]
        trading_days = [date(2026, 1, i) for i in (2, 5, 6, 7, 8)]  # 5거래일(주말 제외 가정)
        provider = _BulkByDateProvider(symbols, trading_days)

        result = fetch_universe_ohlcv_cached(
            db, provider, symbols, start=date(2026, 1, 1), end=date(2026, 1, 8)
        )

        # 종목 수(3)가 아니라 거래일 수(5)만큼만 호출됨 — 종목별 호출이 아예 없음을 증명
        # (fetch_ohlcv를 정의하지 않은 스텁이라 호출됐다면 AttributeError로 실패했을 것).
        assert len(provider.bulk_calls) == 5
        for symbol in symbols:
            assert len(result[symbol]) == 5

    def test_progress_reported_per_symbol_not_per_date(self, db):
        symbols = ["005930", "000660"]
        trading_days = [date(2026, 1, i) for i in (2, 5)]
        provider = _BulkByDateProvider(symbols, trading_days)

        calls: list[tuple[int, int]] = []
        fetch_universe_ohlcv_cached(
            db, provider, symbols, start=date(2026, 1, 1), end=date(2026, 1, 5),
            on_progress=lambda done, total: calls.append((done, total)),
        )

        assert all(total == 2 for _, total in calls)  # total=종목 수, 거래일 수(2) 아님
        assert calls[-1][0] == 2  # 두 종목 모두 완료

    def test_one_failing_trading_day_does_not_block_others(self, db):
        symbols = ["005930", "000660"]
        trading_days = [date(2026, 1, i) for i in (2, 5, 6)]
        provider = _BulkByDateProvider(symbols, trading_days, failing_days={date(2026, 1, 5)})

        result = fetch_universe_ohlcv_cached(
            db, provider, symbols, start=date(2026, 1, 1), end=date(2026, 1, 6)
        )

        # 실패한 거래일(1/5)만 빠지고 나머지 2거래일(1/2, 1/6)은 정상 반영됨
        for symbol in symbols:
            assert len(result[symbol]) == 2

    def test_falls_back_to_per_symbol_path_when_provider_lacks_bulk_support(self, db):
        provider = _RecordingOhlcvProvider()  # fetch_ohlcv_bulk_by_date 없음
        fetch_universe_ohlcv_cached(
            db, provider, ["005930"], start=date(2026, 1, 1), end=date(2026, 1, 3)
        )
        assert provider.calls  # 기존 종목별 경로가 정상적으로 쓰임(회귀 없음)
