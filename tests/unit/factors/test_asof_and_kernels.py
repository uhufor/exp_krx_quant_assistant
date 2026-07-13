from __future__ import annotations

import numpy as np
import pandas as pd

from quant_krx.factors.asof import align_financials
from quant_krx.factors.kernels import (
    eps_growth_kernel,
    per_kernel,
    safe_divide_nonzero,
    safe_divide_positive,
    step_growth,
)


def _financials_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["disclosure_date"] = pd.to_datetime(df["disclosure_date"])
    return df


def test_align_financials_nan_before_first_disclosure():
    financials = _financials_frame([
        {"fiscal_year": 2024, "fiscal_quarter": 1, "statement_scope": "consolidated",
         "revenue": 100.0, "period_end": "2024-03-31", "disclosure_date": "2024-05-15"},
    ])
    daily_index = pd.date_range("2024-01-01", "2024-06-01", freq="D")
    aligned = align_financials(financials, daily_index)
    before = aligned.loc[:"2024-05-14", "revenue"]
    after = aligned.loc["2024-05-15":, "revenue"]
    assert before.isna().all()
    assert (after == 100.0).all()


def test_align_financials_tie_break_prefers_latest_period_end():
    financials = _financials_frame([
        {"fiscal_year": 2024, "fiscal_quarter": 1, "statement_scope": "consolidated",
         "revenue": 100.0, "period_end": "2024-03-31", "disclosure_date": "2024-08-14"},
        {"fiscal_year": 2024, "fiscal_quarter": 2, "statement_scope": "consolidated",
         "revenue": 200.0, "period_end": "2024-06-30", "disclosure_date": "2024-08-14"},
    ])
    daily_index = pd.date_range("2024-08-13", "2024-08-15", freq="D")
    aligned = align_financials(financials, daily_index)
    assert aligned.loc["2024-08-14", "revenue"] == 200.0
    assert aligned.loc["2024-08-15", "revenue"] == 200.0
    assert pd.isna(aligned.loc["2024-08-13", "revenue"])


def test_align_financials_falls_back_to_separate_when_consolidated_absent():
    financials = _financials_frame([
        {"fiscal_year": 2024, "fiscal_quarter": 1, "statement_scope": "separate",
         "revenue": 50.0, "period_end": "2024-03-31", "disclosure_date": "2024-05-15"},
    ])
    daily_index = pd.date_range("2024-05-15", "2024-05-20", freq="D")
    aligned = align_financials(financials, daily_index)
    assert (aligned["revenue"] == 50.0).all()


def test_align_financials_prefers_consolidated_over_separate_same_period():
    financials = _financials_frame([
        {"fiscal_year": 2024, "fiscal_quarter": 1, "statement_scope": "separate",
         "revenue": 50.0, "period_end": "2024-03-31", "disclosure_date": "2024-05-14"},
        {"fiscal_year": 2024, "fiscal_quarter": 1, "statement_scope": "consolidated",
         "revenue": 100.0, "period_end": "2024-03-31", "disclosure_date": "2024-05-15"},
    ])
    daily_index = pd.date_range("2024-05-15", "2024-05-16", freq="D")
    aligned = align_financials(financials, daily_index)
    assert (aligned["revenue"] == 100.0).all()


def test_safe_divide_positive_nan_on_nonpositive_denominator():
    num = pd.Series([10.0, 10.0, 10.0])
    den = pd.Series([2.0, 0.0, -1.0])
    result = safe_divide_positive(num, den)
    assert result.iloc[0] == 5.0
    assert result.iloc[1:].isna().all()


def test_safe_divide_nonzero_allows_negative_denominator():
    num = pd.Series([10.0, 10.0])
    den = pd.Series([0.0, -2.0])
    result = safe_divide_nonzero(num, den)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == -5.0


def test_per_kernel_matches_close_over_eps():
    close = pd.Series([100.0, 100.0])
    eps = pd.Series([10.0, -5.0])
    result = per_kernel(close, eps)
    assert result.iloc[0] == 10.0
    assert pd.isna(result.iloc[1])


def test_step_growth_first_step_is_insufficient_history_nan():
    eps = pd.Series([10.0, 10.0, 10.0])
    result = step_growth(eps)
    assert result.isna().all()  # 스텝 변경이 한 번도 없으면(단일 스텝) 항상 NaN


def test_step_growth_holds_value_between_step_changes():
    eps = pd.Series([10.0, 10.0, 12.0, 12.0, 12.0, 15.0])
    result = step_growth(eps)
    # 첫 스텝(10)은 직전 스텝 없음 → NaN
    # 12로 변경 시 (12-10)/10=0.2, 유지, 15로 변경 시 (15-12)/12=0.25
    expected = pd.Series([np.nan, np.nan, 0.2, 0.2, 0.2, 0.25])
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_step_growth_nan_when_prior_step_non_positive():
    eps = pd.Series([-5.0, -5.0, 10.0, 10.0])
    result = step_growth(eps)
    # 직전 스텝(-5)이 <=0이므로 10으로 바뀌는 시점의 growth도 NaN 유지
    assert result.isna().all()


def test_eps_growth_kernel_delegates_to_step_growth():
    eps = pd.Series([10.0, 10.0, 20.0])
    pd.testing.assert_series_equal(eps_growth_kernel(eps), step_growth(eps))


def test_kernels_do_not_mutate_input():
    eps = pd.Series([10.0, 10.0, 20.0])
    before = eps.copy()
    step_growth(eps)
    pd.testing.assert_series_equal(eps, before)
