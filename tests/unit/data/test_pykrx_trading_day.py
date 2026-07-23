from __future__ import annotations

from datetime import date

import pandas as pd

from quant_krx.data.pykrx_adapter import PyKrxAdapter


class _StubStock:
    """휴장일 조회 시 빈 결과, 보정된 영업일 조회 시 정상 결과를 흉내내는 스텁."""

    def __init__(self, *, business_day: str, holiday: str):
        self.business_day = business_day
        self.holiday = holiday
        self.requested_dates: list[str] = []

    def get_nearest_business_day_in_a_week(self, date_str: str, prev: bool = True) -> str:
        return self.business_day if date_str == self.holiday else date_str

    def get_market_ticker_list(self, date_str: str, market: str = "KOSPI") -> list[str]:
        self.requested_dates.append(date_str)
        if date_str == self.holiday:
            return []
        return ["005930"] if market == "KOSPI" else ["247540"]

    def get_market_ohlcv_by_ticker(self, date_str: str, market: str = "KOSPI") -> pd.DataFrame:
        self.requested_dates.append(date_str)
        if date_str == self.holiday:
            return pd.DataFrame(columns=["시가", "고가", "저가", "종가", "거래량", "거래대금"])
        idx = ["005930"] if market == "KOSPI" else ["247540"]
        return pd.DataFrame(
            {
                "시가": [69000], "고가": [71000], "저가": [68000],
                "종가": [70000], "거래량": [1000], "거래대금": [70000000],
            },
            index=idx,
        )

    def get_previous_business_days(self, fromdate: str, todate: str) -> list:
        self.requested_dates.append((fromdate, todate))
        return [pd.Timestamp(d) for d in ("2026-07-20", "2026-07-21", "2026-07-22")]


def test_list_symbols_falls_back_to_nearest_business_day_on_holiday(monkeypatch):
    stub = _StubStock(business_day="20260722", holiday="20260723")
    monkeypatch.setattr("quant_krx.data.pykrx_adapter._krx_stock", lambda: stub)
    monkeypatch.setattr(
        "quant_krx.data.pykrx_adapter.date",
        type("_D", (), {"today": staticmethod(lambda: date(2026, 7, 23))}),
    )

    adapter = PyKrxAdapter()
    symbols = adapter.list_symbols(market="KRX")

    assert symbols == ["005930", "247540"]
    assert "20260723" not in stub.requested_dates
    assert stub.requested_dates == ["20260722", "20260722"]


def test_list_symbols_uses_requested_date_directly_when_it_is_a_trading_day(monkeypatch):
    stub = _StubStock(business_day="20260722", holiday="20260723")
    monkeypatch.setattr("quant_krx.data.pykrx_adapter._krx_stock", lambda: stub)
    monkeypatch.setattr(
        "quant_krx.data.pykrx_adapter.date",
        type("_D", (), {"today": staticmethod(lambda: date(2026, 7, 22))}),
    )

    adapter = PyKrxAdapter()
    symbols = adapter.list_symbols(market="KRX")

    assert symbols == ["005930", "247540"]
    assert stub.requested_dates == ["20260722", "20260722"]


def test_fetch_market_snapshot_falls_back_to_nearest_business_day_on_holiday(monkeypatch):
    stub = _StubStock(business_day="20260722", holiday="20260723")
    monkeypatch.setattr("quant_krx.data.pykrx_adapter._krx_stock", lambda: stub)

    adapter = PyKrxAdapter()
    snapshot = adapter.fetch_market_snapshot(date(2026, 7, 23), market="KRX")

    assert not snapshot.empty
    assert "20260723" not in stub.requested_dates
    assert stub.requested_dates == ["20260722", "20260722"]


def test_business_day_resolution_failure_falls_back_to_original_date(monkeypatch):
    """달력 조회 자체가 실패하는 극단적 환경에서도 원본 로직(빈 결과 시 [] 반환)이
    유지되어 list_symbols가 새로운 예외를 추가로 던지지 않는다."""

    class _BrokenCalendarStock(_StubStock):
        def get_nearest_business_day_in_a_week(self, date_str: str, prev: bool = True) -> str:
            raise RuntimeError("실제 KRX 서버에 해당 일자의 영업일 캘린더가 없음")

    stub = _BrokenCalendarStock(business_day="20260722", holiday="20260723")
    monkeypatch.setattr("quant_krx.data.pykrx_adapter._krx_stock", lambda: stub)
    monkeypatch.setattr(
        "quant_krx.data.pykrx_adapter.date",
        type("_D", (), {"today": staticmethod(lambda: date(2026, 7, 23))}),
    )

    adapter = PyKrxAdapter()
    symbols = adapter.list_symbols(market="KRX")

    assert symbols == []
    assert stub.requested_dates == ["20260723", "20260723"]


def test_list_trading_days_returns_dates_from_pykrx(monkeypatch):
    stub = _StubStock(business_day="20260722", holiday="20260723")
    monkeypatch.setattr("quant_krx.data.pykrx_adapter._krx_stock", lambda: stub)

    adapter = PyKrxAdapter()
    days = adapter.list_trading_days(date(2026, 7, 20), date(2026, 7, 22))

    assert days == [date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22)]
    assert stub.requested_dates == [("20260720", "20260722")]


def test_fetch_ohlcv_bulk_by_date_returns_full_ohlcv_for_all_symbols(monkeypatch):
    stub = _StubStock(business_day="20260722", holiday="20260723")
    monkeypatch.setattr("quant_krx.data.pykrx_adapter._krx_stock", lambda: stub)

    adapter = PyKrxAdapter()
    df = adapter.fetch_ohlcv_bulk_by_date(date(2026, 7, 22), market="KRX")

    assert set(df.columns) == {"symbol", "date", "open", "high", "low", "close", "volume"}
    assert set(df["symbol"]) == {"005930", "247540"}
    row = df[df["symbol"] == "005930"].iloc[0]
    assert row["open"] == 69000 and row["high"] == 71000 and row["low"] == 68000
    assert row["close"] == 70000 and row["volume"] == 1000


def test_fetch_ohlcv_bulk_by_date_falls_back_to_nearest_business_day_on_holiday(monkeypatch):
    stub = _StubStock(business_day="20260722", holiday="20260723")
    monkeypatch.setattr("quant_krx.data.pykrx_adapter._krx_stock", lambda: stub)

    adapter = PyKrxAdapter()
    df = adapter.fetch_ohlcv_bulk_by_date(date(2026, 7, 23), market="KRX")

    assert not df.empty
    assert "20260723" not in stub.requested_dates
