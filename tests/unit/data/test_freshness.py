from __future__ import annotations

from datetime import date

import pytest

from quant_krx.data.coverage import is_financials_stale
from quant_krx.data.freshness import check_freshness
from quant_krx.storage.db import Database

AS_OF = date(2024, 12, 18)
SYMBOLS = ["005930", "000660"]


@pytest.fixture
def db(tmp_path):
    d = Database(path=tmp_path / "fresh.duckdb")
    d.connect()
    yield d
    d.close()


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    """자격증명 경고가 다른 단언을 오염시키지 않도록 기본은 '있음'으로 둔다."""
    monkeypatch.setenv("KRX_ID", "x")
    monkeypatch.setenv("KRX_PW", "x")
    monkeypatch.setenv("DART_API_KEY", "x")


def _put_valuation(db, symbol: str, day: date) -> None:
    """NOT NULL 컬럼만 채운 최소 삽입 — 신선도는 날짜 커버리지만 보므로 지표값은 무관하다."""
    with db.cursor() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO fundamental_daily (symbol, date, close) VALUES (?, ?, ?)",
            [symbol, day, 50000.0],
        )


def _put_financials(db, symbol: str, year: int, quarter: int) -> None:
    with db.cursor() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO financial_statements "
            "(symbol, fiscal_year, fiscal_quarter, statement_scope, period_end) "
            "VALUES (?, ?, ?, ?, ?)",
            [symbol, year, quarter, "consolidated", date(year, quarter * 3, 28)],
        )


# --- is_financials_stale (판정 기준) ---


def test_no_data_is_stale():
    assert is_financials_stale(None, AS_OF) is True


def test_recent_quarter_is_fresh():
    """직전 분기가 있고 다음 분기 공시 유예가 아직 안 지났으면 신선하다."""
    assert is_financials_stale((2024, 3), AS_OF) is False


def test_old_quarter_is_stale():
    assert is_financials_stale((2023, 1), AS_OF) is True


def test_year_boundary_quarter_rollover():
    """4분기 다음은 이듬해 1분기 — 연도 경계에서 판정이 어긋나면 매년 오경보가 난다."""
    assert is_financials_stale((2024, 4), date(2025, 1, 5)) is False
    assert is_financials_stale((2023, 4), date(2025, 1, 5)) is True


# --- check_freshness ---


def test_all_fresh_reports_ok(db):
    for s in SYMBOLS:
        _put_valuation(db, s, AS_OF)
        _put_financials(db, s, 2024, 3)

    report = check_freshness(db, SYMBOLS, as_of=AS_OF)

    assert report.ok is True
    assert report.severity == "ok"
    assert report.summary() == "", "정상일 때는 리포트에 아무것도 붙이지 않는다"


def test_missing_valuation_is_flagged(db):
    for s in SYMBOLS:
        _put_financials(db, s, 2024, 3)

    report = check_freshness(db, SYMBOLS, as_of=AS_OF)

    kinds = {i.kind for i in report.issues}
    assert "valuation" in kinds
    assert any(i.affected == 2 for i in report.issues if i.kind == "valuation")
    assert "밸류에이션" in report.summary()


def test_stale_financials_is_flagged(db):
    for s in SYMBOLS:
        _put_valuation(db, s, AS_OF)
        _put_financials(db, s, 2022, 1)

    report = check_freshness(db, SYMBOLS, as_of=AS_OF)

    assert "financials" in {i.kind for i in report.issues}
    assert "재무제표" in report.summary()


def test_partial_staleness_counts_only_affected(db):
    _put_valuation(db, "005930", AS_OF)
    _put_financials(db, "005930", 2024, 3)
    _put_financials(db, "000660", 2024, 3)   # 000660만 밸류에이션 없음

    report = check_freshness(db, SYMBOLS, as_of=AS_OF)

    val = [i for i in report.issues if i.kind == "valuation"]
    assert len(val) == 1
    assert val[0].affected == 1


def test_missing_krx_credentials_flagged(db, monkeypatch):
    monkeypatch.delenv("KRX_ID", raising=False)
    for s in SYMBOLS:
        _put_valuation(db, s, AS_OF)
        _put_financials(db, s, 2024, 3)

    report = check_freshness(db, SYMBOLS, as_of=AS_OF)

    assert any(i.kind == "credentials" and "KRX" in i.message for i in report.issues)


def test_missing_dart_key_flagged(db, monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    for s in SYMBOLS:
        _put_valuation(db, s, AS_OF)
        _put_financials(db, s, 2024, 3)

    report = check_freshness(db, SYMBOLS, as_of=AS_OF)

    assert any(i.kind == "credentials" and "DART" in i.message for i in report.issues)


def test_credentials_not_checked_when_data_not_needed(db, monkeypatch):
    """밸류에이션·재무를 안 쓰는 전략만 돌 때는 자격증명 부재가 문제가 아니다."""
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("DART_API_KEY", raising=False)

    report = check_freshness(
        db, SYMBOLS, as_of=AS_OF, check_valuation=False, check_financials=False
    )

    assert report.ok is True


def test_missing_ohlcv_is_flagged(db):
    for s in SYMBOLS:
        _put_valuation(db, s, AS_OF)
        _put_financials(db, s, 2024, 3)

    report = check_freshness(db, SYMBOLS, as_of=AS_OF, missing_ohlcv=3)

    assert any(i.kind == "ohlcv" and i.affected == 3 for i in report.issues)


def test_empty_symbols_skips_db_checks(db):
    report = check_freshness(db, [], as_of=AS_OF)
    assert report.checked_symbols == 0
    assert report.ok is True


def test_summary_joins_multiple_issues(db):
    report = check_freshness(db, SYMBOLS, as_of=AS_OF, missing_ohlcv=1)
    assert len(report.issues) >= 2
    assert " · " in report.summary()


def test_check_is_deterministic(db):
    for s in SYMBOLS:
        _put_financials(db, s, 2022, 1)
    first = check_freshness(db, SYMBOLS, as_of=AS_OF)
    second = check_freshness(db, SYMBOLS, as_of=AS_OF)
    assert first == second
