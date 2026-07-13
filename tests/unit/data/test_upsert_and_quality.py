from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
import pytest

from quant_krx.data.quality import QualityViolation, apply_quality_gate
from quant_krx.data.schema import FUNDAMENTAL_SCHEMA_SQL
from quant_krx.data.upsert import upsert_fundamental
from quant_krx.storage.schema import SCHEMA_SQL


@pytest.fixture
def conn(tmp_path):
    c = duckdb.connect(str(tmp_path / "test.duckdb"))
    c.execute(SCHEMA_SQL)
    c.execute(FUNDAMENTAL_SCHEMA_SQL)
    yield c
    c.close()


def _valuation_row(symbol="005930", d="2024-01-02", **overrides):
    base = dict(
        symbol=symbol, date=d, close=70000.0, per=10.0, pbr=1.5, eps=7000.0, bps=46000.0,
        div=0.02, dps=1400.0, market_cap=1e12, shares=1e7, source="test", fetched_at=None,
    )
    base.update(overrides)
    return base


def test_upsert_idempotent_reexecution(conn):
    frame = pd.DataFrame(
        [_valuation_row(d="2024-01-02"), _valuation_row(d="2024-01-03")]
    ).assign(fetched_at=pd.Timestamp.utcnow())
    r1 = upsert_fundamental(conn, "fundamental_daily", frame, as_of=date(2024, 1, 5))
    r2 = upsert_fundamental(conn, "fundamental_daily", frame, as_of=date(2024, 1, 5))
    assert r1.accepted == 2
    assert r2.accepted == 2
    count = conn.execute("SELECT COUNT(*) FROM fundamental_daily").fetchone()[0]
    assert count == 2  # 재실행에도 중복 0


def test_upsert_excludes_duplicate_pk_within_batch(conn):
    frame = pd.DataFrame(
        [_valuation_row(d="2024-01-02", close=100.0), _valuation_row(d="2024-01-02", close=200.0)]
    ).assign(fetched_at=pd.Timestamp.utcnow())
    result = upsert_fundamental(conn, "fundamental_daily", frame, as_of=date(2024, 1, 5))
    assert result.accepted == 1
    assert len(result.excluded) == 1
    assert result.excluded[0].reason == QualityViolation.DUPLICATE_PK


def test_upsert_excludes_future_date(conn):
    frame = pd.DataFrame([_valuation_row(d="2099-01-01")]).assign(
        fetched_at=pd.Timestamp.utcnow()
    )
    result = upsert_fundamental(conn, "fundamental_daily", frame, as_of=date(2024, 1, 5))
    assert result.accepted == 0
    assert result.excluded[0].reason == QualityViolation.FUTURE_DATE


def test_upsert_excludes_negative_market_cap_and_shares(conn):
    frame = pd.DataFrame(
        [_valuation_row(d="2024-01-02", market_cap=-1.0),
         _valuation_row(d="2024-01-03", shares=-5.0)]
    ).assign(fetched_at=pd.Timestamp.utcnow())
    result = upsert_fundamental(conn, "fundamental_daily", frame, as_of=date(2024, 1, 5))
    assert result.accepted == 0
    assert all(e.reason == QualityViolation.NEGATIVE_FIELD for e in result.excluded)


def test_quality_gate_excludes_non_ascending_date_per_symbol():
    frame = pd.DataFrame(
        [
            _valuation_row(d="2024-01-05"),
            _valuation_row(d="2024-01-02"),  # 직전 행(01-05)보다 앞선 날짜
        ]
    )
    accepted, excluded = apply_quality_gate(
        "fundamental_daily", frame, as_of=date(2024, 1, 10)
    )
    assert len(accepted) == 1
    assert excluded[0].reason == QualityViolation.NON_ASCENDING_DATE


def test_quality_gate_empty_frame_returns_no_exclusions():
    accepted, excluded = apply_quality_gate(
        "fundamental_daily", pd.DataFrame(), as_of=date(2024, 1, 1)
    )
    assert accepted.empty
    assert excluded == ()


def test_upsert_financial_statements_idempotent(conn):
    row = dict(
        symbol="005930", fiscal_year=2024, fiscal_quarter=1, statement_scope="consolidated",
        revenue=1000.0, gross_profit=350.0, operating_income=150.0, net_income=100.0,
        pretax_income=130.0, income_tax=30.0, total_assets=5000.0, total_debt=1500.0,
        total_equity=3500.0, current_assets=2000.0, current_liabilities=750.0,
        operating_cash_flow=160.0, interest_expense=10.0, depreciation_amortization=50.0,
        cash_and_equivalents=500.0, invested_capital=5000.0,
        period_end="2024-03-31", disclosure_date="2024-05-15",
        source="test", fetched_at=pd.Timestamp.utcnow(),
    )
    frame = pd.DataFrame([row])
    r1 = upsert_fundamental(conn, "financial_statements", frame, as_of=date(2024, 6, 1))
    r2 = upsert_fundamental(conn, "financial_statements", frame, as_of=date(2024, 6, 1))
    assert r1.accepted == 1
    assert r2.accepted == 1
    count = conn.execute("SELECT COUNT(*) FROM financial_statements").fetchone()[0]
    assert count == 1
