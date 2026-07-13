from __future__ import annotations

import pandas as pd
import pytest

from quant_krx.factors.base import FactorInput
from quant_krx.factors.dispatch import compute_factor
from quant_krx.factors.notes import FactorNote, get_factor_notes
from quant_krx.factors.registry import get_factor

FINANCIAL_IDS = [
    "psr", "pcr", "ev_ebitda", "roa", "roic", "gross_margin", "operating_margin",
    "net_margin", "gp_to_assets", "revenue_growth", "op_income_growth",
    "debt_to_equity", "current_ratio", "interest_coverage",
]
NEEDS_VALUATION = {"psr", "pcr", "ev_ebitda"}


def _quarter_row(fy, fq, **overrides):
    pe = pd.Timestamp(year=fy, month=3 * fq, day=1)
    disc = pe + pd.Timedelta(days=45)
    base = dict(
        symbol="TEST", fiscal_year=fy, fiscal_quarter=fq, statement_scope="consolidated",
        revenue=1000.0, gross_profit=350.0, operating_income=150.0, net_income=100.0,
        pretax_income=130.0, income_tax=30.0, total_assets=5000.0, total_debt=1500.0,
        total_equity=3500.0, current_assets=2000.0, current_liabilities=750.0,
        operating_cash_flow=160.0, interest_expense=10.0, depreciation_amortization=50.0,
        cash_and_equivalents=500.0, invested_capital=5000.0,
        period_end=pe.date(), disclosure_date=disc.date(),
    )
    base.update(overrides)
    return base


@pytest.fixture
def idx() -> pd.DatetimeIndex:
    return pd.date_range("2022-01-01", periods=600, freq="D")


@pytest.fixture
def six_quarters() -> pd.DataFrame:
    rows = [
        _quarter_row(fy, fq, revenue=1000.0 * (1 + 0.1 * i), operating_income=150.0 * (1 + 0.1 * i))
        for i, (fy, fq) in enumerate(
            [(2022, 1), (2022, 2), (2022, 3), (2022, 4), (2023, 1), (2023, 2)]
        )
    ]
    return pd.DataFrame(rows)


def _fi(idx, financials, valuation_market_cap=1e9) -> FactorInput:
    ohlcv = pd.DataFrame({"close": [100.0] * len(idx)}, index=idx)
    valuation = pd.DataFrame({"market_cap": [valuation_market_cap] * len(idx)}, index=idx)
    return FactorInput(ohlcv=ohlcv, valuation=valuation, financials=financials)


@pytest.mark.parametrize("factor_id", FINANCIAL_IDS)
def test_determinism_two_calls_equal(idx, six_quarters, factor_id):
    fi = _fi(idx, six_quarters)
    factor = get_factor(factor_id)
    r1 = compute_factor(factor, fi)
    r2 = compute_factor(factor, fi)
    pd.testing.assert_frame_equal(r1, r2)


@pytest.mark.parametrize("factor_id", FINANCIAL_IDS)
def test_financials_frame_not_mutated(idx, six_quarters, factor_id):
    fi = _fi(idx, six_quarters)
    before = six_quarters.copy(deep=True)
    compute_factor(get_factor(factor_id), fi)
    pd.testing.assert_frame_equal(six_quarters, before)


@pytest.mark.parametrize("factor_id", FINANCIAL_IDS)
def test_output_columns_match_metadata(idx, six_quarters, factor_id):
    fi = _fi(idx, six_quarters)
    factor = get_factor(factor_id)
    result = compute_factor(factor, fi)
    assert set(result.columns) == set(factor.metadata.output)
    assert result.index.equals(idx)


@pytest.mark.parametrize("factor_id", FINANCIAL_IDS)
def test_degrade_when_financials_none(idx, factor_id):
    fi = FactorInput(
        ohlcv=pd.DataFrame({"close": [1.0] * len(idx)}, index=idx),
        valuation=pd.DataFrame({"market_cap": [1e9] * len(idx)}, index=idx),
        financials=None,
    )
    factor = get_factor(factor_id)
    result = compute_factor(factor, fi)
    col = factor.metadata.output[0]
    assert result[col].isna().all()
    assert get_factor_notes(result)[col] == FactorNote.MISSING_INPUT


@pytest.mark.parametrize("factor_id", sorted(NEEDS_VALUATION))
def test_degrade_when_valuation_none_for_valuation_dependent(idx, six_quarters, factor_id):
    fi = FactorInput(ohlcv=pd.DataFrame({"close": [1.0] * len(idx)}, index=idx),
                      valuation=None, financials=six_quarters)
    factor = get_factor(factor_id)
    result = compute_factor(factor, fi)
    col = factor.metadata.output[0]
    assert result[col].isna().all()
    assert get_factor_notes(result)[col] == FactorNote.MISSING_INPUT


def test_psr_parity_after_first_disclosure(idx, six_quarters):
    fi = _fi(idx, six_quarters, valuation_market_cap=1e9)
    result = compute_factor(get_factor("psr"), fi)
    last_disclosure = pd.Timestamp(six_quarters["disclosure_date"].max())
    last_revenue = six_quarters.sort_values("disclosure_date")["revenue"].iloc[-1]
    expected = 1e9 / last_revenue
    assert result.loc[idx[idx >= last_disclosure][-1], "psr"] == pytest.approx(expected)


def test_revenue_growth_matches_manual_yoy(idx, six_quarters):
    fi = _fi(idx, six_quarters)
    result = compute_factor(get_factor("revenue_growth"), fi)
    last_date = idx[-1]
    # 6분기 중 마지막(2023Q2, i=5) vs 4분기 전(2022Q2, i=1): (1500-1100)/1100
    expected = (1000.0 * 1.5 - 1000.0 * 1.1) / (1000.0 * 1.1)
    assert result.loc[last_date, "revenue_growth"] == pytest.approx(expected)


def test_revenue_growth_insufficient_history_with_fewer_than_5_quarters(idx):
    rows = [_quarter_row(2023, q) for q in (1, 2, 3)]
    financials = pd.DataFrame(rows)
    fi = _fi(idx, financials)
    result = compute_factor(get_factor("revenue_growth"), fi)
    assert result["revenue_growth"].isna().all()
    assert get_factor_notes(result)["revenue_growth"] == FactorNote.INSUFFICIENT_HISTORY


def test_revenue_growth_non_positive_denominator_when_prior_year_nonpositive(idx):
    rows = [
        _quarter_row(2022, 1, revenue=-100.0), _quarter_row(2022, 2, revenue=-100.0),
        _quarter_row(2022, 3, revenue=-100.0), _quarter_row(2022, 4, revenue=-100.0),
        _quarter_row(2023, 1, revenue=1000.0),
    ]
    financials = pd.DataFrame(rows)
    fi = _fi(idx, financials)
    result = compute_factor(get_factor("revenue_growth"), fi)
    last_date = idx[-1]
    assert pd.isna(result.loc[last_date, "revenue_growth"])
    assert get_factor_notes(result)["revenue_growth"] == FactorNote.NON_POSITIVE_DENOMINATOR


def test_debt_to_equity_non_positive_denominator_on_capital_impairment(idx):
    rows = [_quarter_row(2023, 1, total_equity=-500.0)]
    financials = pd.DataFrame(rows)
    fi = _fi(idx, financials)
    result = compute_factor(get_factor("debt_to_equity"), fi)
    assert get_factor_notes(result)["debt_to_equity"] == FactorNote.NON_POSITIVE_DENOMINATOR


def test_interest_coverage_zero_denominator(idx):
    rows = [_quarter_row(2023, 1, interest_expense=0.0)]
    financials = pd.DataFrame(rows)
    fi = _fi(idx, financials)
    result = compute_factor(get_factor("interest_coverage"), fi)
    assert get_factor_notes(result)["interest_coverage"] == FactorNote.ZERO_DENOMINATOR


def test_roic_tax_rate_clamped_and_invested_capital_nonpositive(idx):
    rows = [_quarter_row(2023, 1, invested_capital=-1.0)]
    financials = pd.DataFrame(rows)
    fi = _fi(idx, financials)
    result = compute_factor(get_factor("roic"), fi)
    assert get_factor_notes(result)["roic"] == FactorNote.NON_POSITIVE_DENOMINATOR


def test_consolidated_preferred_over_separate_in_financial_ratios(idx):
    rows = [
        _quarter_row(2023, 1, statement_scope="separate", revenue=500.0),
        _quarter_row(2023, 1, statement_scope="consolidated", revenue=1000.0),
    ]
    financials = pd.DataFrame(rows)
    fi = _fi(idx, financials)
    result = compute_factor(get_factor("gross_margin"), fi)
    last_date = idx[-1]
    assert result.loc[last_date, "gross_margin"] == pytest.approx(350.0 / 1000.0)


def test_registry_has_32_factors_after_financial_catalog():
    from quant_krx.factors.registry import list_factors

    assert len(list_factors()) == 32
