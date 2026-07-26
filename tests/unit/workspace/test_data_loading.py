from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.data.coverage import date_range_gaps, existing_financials_periods
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import StrategyDefinition, Universe
from quant_krx.workspace.data_loading import (
    fetch_and_upsert_fundamentals,
    resolve_backtest_symbols,
)


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


class _RecordingFinancialsProvider:
    """financials 증분 수집(financials_kwargs 전달) 검증용 스텁 provider."""

    source_name = "Stub"

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], date, date, dict]] = []

    def fetch_valuation(self, symbols, start, end) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_financials(self, symbols, start, end, **kwargs) -> pd.DataFrame:
        self.calls.append((list(symbols), start, end, kwargs))
        rows = [
            {
                "symbol": symbol, "fiscal_year": 2025, "fiscal_quarter": 1,
                "statement_scope": "consolidated",
                "revenue": 100.0, "gross_profit": 50.0, "operating_income": 30.0,
                "net_income": 20.0, "pretax_income": 25.0, "income_tax": 5.0,
                "total_assets": 1000.0, "total_debt": 400.0, "total_equity": 600.0,
                "current_assets": 500.0, "current_liabilities": 200.0,
                "operating_cash_flow": 40.0, "interest_expense": 2.0,
                "depreciation_amortization": 10.0, "cash_and_equivalents": 100.0,
                "invested_capital": 1000.0,
                "period_end": date(2025, 3, 31), "disclosure_date": date(2025, 5, 15),
            }
            for symbol in symbols
        ]
        return pd.DataFrame(rows)


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "test.duckdb")
    database.connect()
    yield database
    database.close()


def _strategy(symbols: tuple[str, ...] = ()) -> StrategyDefinition:
    from quant_krx.strategy.definition import FactorRef

    return StrategyDefinition(
        id="s", name="s", version="1",
        factor_refs=(FactorRef("sma", {}),),
        universe=Universe(symbols=symbols),
    )


class TestResolveBacktestSymbols:
    """watchlist(daily job 전용)는 ad-hoc 백테스트(CLI/GUI) 심볼 해석에 관여하지 않는다."""

    def test_explicit_request_wins_over_universe(self):
        defn = _strategy(symbols=("005930",))
        assert resolve_backtest_symbols(defn, ["035720"]) == ["035720"]

    def test_falls_back_to_universe_when_no_request(self):
        defn = _strategy(symbols=("005930", "000660"))
        assert resolve_backtest_symbols(defn, None) == ["005930", "000660"]

    def test_empty_universe_and_no_request_returns_empty_not_watchlist(self):
        defn = _strategy(symbols=())
        assert resolve_backtest_symbols(defn, None) == []


class TestGapRanges:
    def test_no_existing_data_returns_full_range(self):
        assert date_range_gaps(None, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 10))
        ]

    def test_fully_covered_returns_no_gaps(self):
        existing = (date(2026, 1, 1), date(2026, 1, 10))
        assert date_range_gaps(existing, date(2026, 1, 3), date(2026, 1, 8)) == []

    def test_before_gap_only(self):
        existing = (date(2026, 1, 5), date(2026, 1, 10))
        assert date_range_gaps(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 4))
        ]

    def test_after_gap_only(self):
        existing = (date(2026, 1, 1), date(2026, 1, 5))
        assert date_range_gaps(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 6), date(2026, 1, 10))
        ]

    def test_both_gaps(self):
        existing = (date(2026, 1, 5), date(2026, 1, 6))
        assert date_range_gaps(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 4)),
            (date(2026, 1, 7), date(2026, 1, 10)),
        ]

    def test_disjoint_existing_before_request(self):
        existing = (date(2025, 1, 1), date(2025, 1, 5))
        assert date_range_gaps(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
            (date(2026, 1, 1), date(2026, 1, 10))
        ]

    def test_disjoint_existing_after_request(self):
        existing = (date(2026, 2, 1), date(2026, 2, 5))
        assert date_range_gaps(existing, date(2026, 1, 1), date(2026, 1, 10)) == [
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


class TestFinancialsIncremental:
    """financials 증분 수집(TRD-R04 §1) — financials_kwargs 전달 경로 검증."""

    def test_existing_financials_periods_empty_when_no_data(self, db):
        with db.cursor() as conn:
            assert existing_financials_periods(conn, ["005930"]) == {}

    def test_existing_financials_periods_reflects_upserted_rows(self, db):
        provider = _RecordingFinancialsProvider()
        fetch_and_upsert_fundamentals(
            db, ["005930"], provider,
            start=date(2025, 1, 1), end=date(2025, 12, 31),
            as_of=date(2025, 12, 31), kinds=frozenset({"financials"}),
        )
        with db.cursor() as conn:
            coverage = existing_financials_periods(conn, ["005930"])
        assert coverage == {"005930": {(2025, 1)}}

    def test_financials_kwargs_forwarded_to_provider(self, db):
        provider = _RecordingFinancialsProvider()
        skip = {"005930": {(2024, 4)}}
        fetch_and_upsert_fundamentals(
            db, ["005930"], provider,
            start=date(2025, 1, 1), end=date(2025, 12, 31),
            as_of=date(2025, 12, 31), kinds=frozenset({"financials"}),
            financials_kwargs={"skip_periods": skip},
        )
        assert provider.calls == [
            (["005930"], date(2025, 1, 1), date(2025, 12, 31), {"skip_periods": skip})
        ]

    def test_no_financials_kwargs_calls_provider_without_extra_args(self, db):
        provider = _RecordingFinancialsProvider()
        fetch_and_upsert_fundamentals(
            db, ["005930"], provider,
            start=date(2025, 1, 1), end=date(2025, 12, 31),
            as_of=date(2025, 12, 31), kinds=frozenset({"financials"}),
        )
        assert provider.calls == [(["005930"], date(2025, 1, 1), date(2025, 12, 31), {})]
