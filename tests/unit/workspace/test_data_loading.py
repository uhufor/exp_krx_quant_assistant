from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.storage.db import Database
from quant_krx.workspace.data_loading import _gap_ranges, fetch_and_upsert_fundamentals


class _RecordingValuationProvider:
    """호출 인자를 기록하는 스텁 provider — 증분 fetch 범위 검증용."""

    source_name = "Stub"

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], date, date]] = []

    def fetch_valuation(self, symbols, start, end) -> pd.DataFrame:
        self.calls.append((list(symbols), start, end))
        dates = pd.date_range(start, end, freq="D")
        rows = []
        for symbol in symbols:
            for d in dates:
                rows.append(
                    {
                        "symbol": symbol, "date": d, "close": 100.0, "per": 10.0,
                        "pbr": 1.0, "eps": 10.0, "bps": 100.0, "div": 0.01, "dps": 1.0,
                        "market_cap": 1000.0, "shares": 10.0,
                    }
                )
        return pd.DataFrame(rows)

    def fetch_financials(self, symbols, start, end) -> pd.DataFrame:
        raise NotImplementedError


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

    def test_before_gap_only(self):
        existing = (date(2026, 1, 5), date(2026, 1, 10))
        assert _gap_ranges(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 4))
        ]

    def test_after_gap_only(self):
        existing = (date(2026, 1, 1), date(2026, 1, 5))
        assert _gap_ranges(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 6), date(2026, 1, 10))
        ]

    def test_both_gaps(self):
        existing = (date(2026, 1, 5), date(2026, 1, 6))
        assert _gap_ranges(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 4)),
            (date(2026, 1, 7), date(2026, 1, 10)),
        ]

    def test_disjoint_existing_before_request(self):
        existing = (date(2025, 1, 1), date(2025, 1, 5))
        assert _gap_ranges(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 10))
        ]

    def test_disjoint_existing_after_request(self):
        existing = (date(2026, 2, 1), date(2026, 2, 5))
        assert _gap_ranges(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 10))
        ]


class TestFetchAndUpsertFundamentalsIncremental:
    def test_first_call_fetches_full_range(self, db):
        provider = _RecordingValuationProvider()
        fetch_and_upsert_fundamentals(
            db, ["005930"], provider,
            start=date(2026, 1, 1), end=date(2026, 1, 10),
            as_of=date(2026, 1, 10), kinds=frozenset({"valuation"}),
        )
        assert provider.calls == [(["005930"], date(2026, 1, 1), date(2026, 1, 10))]

    def test_second_call_same_range_skips_provider(self, db):
        provider = _RecordingValuationProvider()
        for _ in range(2):
            fetch_and_upsert_fundamentals(
                db, ["005930"], provider,
                start=date(2026, 1, 1), end=date(2026, 1, 10),
                as_of=date(2026, 1, 10), kinds=frozenset({"valuation"}),
            )
        assert len(provider.calls) == 1  # 두 번째 호출은 이미 커버되어 provider 호출 0회

    def test_extended_end_date_fetches_only_tail_gap(self, db):
        provider = _RecordingValuationProvider()
        fetch_and_upsert_fundamentals(
            db, ["005930"], provider,
            start=date(2026, 1, 1), end=date(2026, 1, 10),
            as_of=date(2026, 1, 20), kinds=frozenset({"valuation"}),
        )
        fetch_and_upsert_fundamentals(
            db, ["005930"], provider,
            start=date(2026, 1, 1), end=date(2026, 1, 15),
            as_of=date(2026, 1, 20), kinds=frozenset({"valuation"}),
        )
        assert provider.calls == [
            (["005930"], date(2026, 1, 1), date(2026, 1, 10)),
            (["005930"], date(2026, 1, 11), date(2026, 1, 15)),
        ]

    def test_ohlcv_only_kinds_skips_provider_entirely(self, db):
        provider = _RecordingValuationProvider()
        fetch_and_upsert_fundamentals(
            db, ["005930"], provider,
            start=date(2026, 1, 1), end=date(2026, 1, 10),
            as_of=date(2026, 1, 10), kinds=frozenset(),
        )
        assert provider.calls == []
