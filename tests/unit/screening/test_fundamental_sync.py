from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.data.coverage import existing_financials_periods, existing_valuation_coverage
from quant_krx.screening.fundamental_sync import (
    _is_stale,
    sync_universe_fundamentals,
)
from quant_krx.storage.db import Database

AS_OF = date(2026, 1, 15)


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "test.duckdb")
    database.connect()
    yield database
    database.close()


def _financials_row(
    symbol: str, fiscal_year: int, fiscal_quarter: int, disclosure_date: date = date(2020, 1, 1)
) -> dict:
    # disclosure_date는 quality gate의 future_date 판정(as_of 기준) 회피를 위해 항상
    # AS_OF보다 충분히 과거인 고정값을 기본값으로 쓴다(실제 공시일과 무관, 테스트 전용).
    return {
        "symbol": symbol, "fiscal_year": fiscal_year, "fiscal_quarter": fiscal_quarter,
        "statement_scope": "consolidated",
        "revenue": 100.0, "gross_profit": 50.0, "operating_income": 30.0,
        "net_income": 20.0, "pretax_income": 25.0, "income_tax": 5.0,
        "total_assets": 1000.0, "total_debt": 400.0, "total_equity": 600.0,
        "current_assets": 500.0, "current_liabilities": 200.0,
        "operating_cash_flow": 40.0, "interest_expense": 2.0,
        "depreciation_amortization": 10.0, "cash_and_equivalents": 100.0,
        "invested_capital": 1000.0,
        "period_end": date(fiscal_year, 3 * fiscal_quarter, 1),
        "disclosure_date": disclosure_date,
    }


class _StubDartAdapter:
    """DartFundamentalAdapter 대역 — 생성 여부·호출 인자를 기록한다."""

    constructed = 0

    def __init__(self) -> None:
        type(self).constructed += 1
        self.calls: list[tuple[list[str], date, dict | None]] = []

    source_name = "DART"

    def fetch_latest_financials(self, symbols, as_of, *, skip_periods=None):
        self.calls.append((list(symbols), as_of, skip_periods))
        rows = [_financials_row(s, 2025, 2) for s in symbols]
        return pd.DataFrame(rows)

    def close(self) -> None:
        pass


class _RaisingDartAdapter:
    def __init__(self) -> None:
        raise RuntimeError("DART_API_KEY 미설정")


class _StubPyKrxFundamentalAdapter:
    constructed = 0

    def __init__(self) -> None:
        type(self).constructed += 1
        self.calls: list[tuple[list[str], date, date]] = []

    source_name = "PyKrx"

    def fetch_valuation(self, symbols, start, end):
        self.calls.append((list(symbols), start, end))
        rows = [
            {
                "symbol": s, "date": start, "close": 100.0, "per": 10.0, "pbr": 1.0,
                "eps": 10.0, "bps": 100.0, "div": 0.01, "dps": 1.0,
                "market_cap": 1000.0, "shares": 10.0,
            }
            for s in symbols
        ]
        return pd.DataFrame(rows)


class TestIsStale:
    def test_no_existing_data_is_stale(self):
        assert _is_stale(None, AS_OF) is True

    def test_recent_quarter_with_next_not_yet_due_is_fresh(self):
        # 2025 Q4(12/31) 보유 중 — 다음 분기(2026 Q1, 3/31)는 아직 유예기간 안 지남.
        assert _is_stale((2025, 4), date(2026, 1, 15)) is False

    def test_old_quarter_past_grace_period_is_stale(self):
        # 2024 Q4(12/31) 보유 중 — 다음 분기(2025 Q1, 3/31)+100일 유예가 이미 지남.
        assert _is_stale((2024, 4), date(2026, 1, 15)) is True


class TestSyncUniverseFundamentals:
    def test_no_needs_flags_touches_nothing(self, db, monkeypatch):
        monkeypatch.setattr(
            "quant_krx.data.dart_fundamental.DartFundamentalAdapter", _StubDartAdapter
        )
        sync_universe_fundamentals(
            db, ["005930"], as_of=AS_OF, needs_valuation=False, needs_financials=False
        )
        assert _StubDartAdapter.constructed == 0

    def test_financials_bypassed_when_already_fresh(self, db, monkeypatch):
        with db.cursor() as conn:
            from quant_krx.data.upsert import upsert_fundamental

            frame = pd.DataFrame([_financials_row("005930", 2025, 4)]).assign(
                source="dart", fetched_at=date.today()
            )
            upsert_fundamental(conn, "financial_statements", frame, as_of=AS_OF)

        monkeypatch.setattr(
            "quant_krx.data.dart_fundamental.DartFundamentalAdapter", _StubDartAdapter
        )
        _StubDartAdapter.constructed = 0

        sync_universe_fundamentals(
            db, ["005930"], as_of=AS_OF, needs_valuation=False, needs_financials=True
        )

        assert _StubDartAdapter.constructed == 0  # 이미 신선 -> DART 어댑터 생성 자체가 없음

    def test_financials_syncs_stale_symbol(self, db, monkeypatch):
        monkeypatch.setattr(
            "quant_krx.data.dart_fundamental.DartFundamentalAdapter", _StubDartAdapter
        )
        _StubDartAdapter.constructed = 0

        sync_universe_fundamentals(
            db, ["005930"], as_of=AS_OF, needs_valuation=False, needs_financials=True
        )

        assert _StubDartAdapter.constructed == 1
        with db.cursor() as conn:
            coverage = existing_financials_periods(conn, ["005930"])
        assert coverage == {"005930": {(2025, 2)}}

    def test_financials_missing_api_key_degrades_without_raising(self, db, monkeypatch):
        monkeypatch.setattr(
            "quant_krx.data.dart_fundamental.DartFundamentalAdapter", _RaisingDartAdapter
        )
        sync_universe_fundamentals(
            db, ["005930"], as_of=AS_OF, needs_valuation=False, needs_financials=True
        )  # 예외 없이 반환되면 통과

    def test_valuation_bypassed_when_already_fresh(self, db, monkeypatch):
        with db.cursor() as conn:
            from quant_krx.data.upsert import upsert_fundamental

            row = {
                "symbol": "005930", "date": AS_OF, "close": 100.0, "per": 10.0, "pbr": 1.0,
                "eps": 10.0, "bps": 100.0, "div": 0.01, "dps": 1.0,
                "market_cap": 1000.0, "shares": 10.0,
            }
            frame = pd.DataFrame([row]).assign(source="pykrx", fetched_at=date.today())
            upsert_fundamental(conn, "fundamental_daily", frame, as_of=AS_OF)

        monkeypatch.setattr(
            "quant_krx.data.pykrx_fundamental.PyKrxFundamentalAdapter",
            _StubPyKrxFundamentalAdapter,
        )
        _StubPyKrxFundamentalAdapter.constructed = 0

        sync_universe_fundamentals(
            db, ["005930"], as_of=AS_OF, needs_valuation=True, needs_financials=False
        )

        assert _StubPyKrxFundamentalAdapter.constructed == 0

    def test_valuation_syncs_stale_symbol(self, db, monkeypatch):
        monkeypatch.setattr(
            "quant_krx.data.pykrx_fundamental.PyKrxFundamentalAdapter",
            _StubPyKrxFundamentalAdapter,
        )
        _StubPyKrxFundamentalAdapter.constructed = 0

        sync_universe_fundamentals(
            db, ["005930"], as_of=AS_OF, needs_valuation=True, needs_financials=False
        )

        assert _StubPyKrxFundamentalAdapter.constructed == 1
        with db.cursor() as conn:
            coverage = existing_valuation_coverage(conn, ["005930"])
        assert coverage["005930"] == (AS_OF, AS_OF)
