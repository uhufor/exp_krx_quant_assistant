from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_krx.factors.base import FactorInput
from quant_krx.factors.dispatch import compute_factor
from quant_krx.factors.notes import FactorNote, get_factor_notes
from quant_krx.factors.registry import get_factor

VALUATION_IDS = [
    "per", "pbr", "earnings_yield", "dividend_yield", "eps", "bps",
    "roe_approx", "payout_ratio", "eps_growth", "peg", "market_cap",
]


@pytest.fixture
def idx() -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=6, freq="D")


@pytest.fixture
def clean_valuation(idx) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "close": [100.0] * 6,
            "eps": [10.0] * 6,
            "bps": [50.0] * 6,
            "div": [0.01] * 6,
            "dps": [2.0] * 6,
            "market_cap": [1e9] * 6,
            "shares": [1e6] * 6,
        },
        index=idx,
    )


def _fi(ohlcv_idx, valuation) -> FactorInput:
    ohlcv = pd.DataFrame({"close": [100.0] * len(ohlcv_idx)}, index=ohlcv_idx)
    return FactorInput(ohlcv=ohlcv, valuation=valuation)


@pytest.mark.parametrize("factor_id", VALUATION_IDS)
def test_determinism_two_calls_equal(idx, clean_valuation, factor_id):
    fi = _fi(idx, clean_valuation)
    factor = get_factor(factor_id)
    r1 = compute_factor(factor, fi)
    r2 = compute_factor(factor, fi)
    pd.testing.assert_frame_equal(r1, r2)


@pytest.mark.parametrize("factor_id", VALUATION_IDS)
def test_valuation_frame_not_mutated(idx, clean_valuation, factor_id):
    fi = _fi(idx, clean_valuation)
    before = clean_valuation.copy(deep=True)
    compute_factor(get_factor(factor_id), fi)
    pd.testing.assert_frame_equal(clean_valuation, before)


@pytest.mark.parametrize("factor_id", VALUATION_IDS)
def test_output_columns_match_metadata(idx, clean_valuation, factor_id):
    fi = _fi(idx, clean_valuation)
    factor = get_factor(factor_id)
    result = compute_factor(factor, fi)
    assert set(result.columns) == set(factor.metadata.output)
    assert result.index.equals(idx)


@pytest.mark.parametrize("factor_id", VALUATION_IDS)
def test_degrade_when_valuation_none(idx, factor_id):
    fi = FactorInput(ohlcv=pd.DataFrame({"close": [1.0] * len(idx)}, index=idx), valuation=None)
    factor = get_factor(factor_id)
    result = compute_factor(factor, fi)
    col = factor.metadata.output[0]
    assert result[col].isna().all()
    assert get_factor_notes(result)[col] == FactorNote.MISSING_INPUT


def test_per_parity_and_nan_on_nonpositive_eps(idx, clean_valuation):
    clean_valuation["eps"] = [10.0, 10.0, -5.0, 0.0, 10.0, 10.0]
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("per"), fi)
    expected = clean_valuation["close"] / clean_valuation["eps"]
    expected[clean_valuation["eps"] <= 0] = np.nan
    pd.testing.assert_series_equal(result["per"], expected, check_names=False)
    assert get_factor_notes(result)["per"] == FactorNote.NON_POSITIVE_DENOMINATOR


def test_pbr_nan_on_nonpositive_bps(idx, clean_valuation):
    clean_valuation["bps"] = [50.0, -10.0, 50.0, 50.0, 50.0, 50.0]
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("pbr"), fi)
    assert pd.isna(result["pbr"].iloc[1])
    assert result["pbr"].iloc[0] == 2.0


def test_earnings_yield_parity(idx, clean_valuation):
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("earnings_yield"), fi)
    expected = clean_valuation["eps"] / clean_valuation["close"]
    pd.testing.assert_series_equal(result["earnings_yield"], expected, check_names=False)


def test_dividend_yield_parity(idx, clean_valuation):
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("dividend_yield"), fi)
    expected = clean_valuation["dps"] / clean_valuation["close"]
    pd.testing.assert_series_equal(result["dividend_yield"], expected, check_names=False)


def test_roe_approx_parity(idx, clean_valuation):
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("roe_approx"), fi)
    expected = clean_valuation["eps"] / clean_valuation["bps"]
    pd.testing.assert_series_equal(result["roe_approx"], expected, check_names=False)


def test_payout_ratio_nan_on_nonpositive_eps(idx, clean_valuation):
    clean_valuation["eps"] = [10.0, 0.0, 10.0, 10.0, 10.0, 10.0]
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("payout_ratio"), fi)
    assert pd.isna(result["payout_ratio"].iloc[1])


def test_eps_passthrough_missing_input_note(idx, clean_valuation):
    clean_valuation["eps"] = [10.0, np.nan, 10.0, 10.0, 10.0, 10.0]
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("eps"), fi)
    assert get_factor_notes(result)["eps"] == FactorNote.MISSING_INPUT


def test_eps_growth_holds_between_steps(idx, clean_valuation):
    clean_valuation["eps"] = [10.0, 10.0, 12.0, 12.0, 12.0, 15.0]
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("eps_growth"), fi)
    expected = pd.Series([np.nan, np.nan, 0.2, 0.2, 0.2, 0.25], index=idx)
    pd.testing.assert_series_equal(result["eps_growth"], expected, check_names=False)
    assert get_factor_notes(result)["eps_growth"] == FactorNote.INSUFFICIENT_HISTORY


def test_eps_growth_non_positive_denominator_note(idx, clean_valuation):
    clean_valuation["eps"] = [-5.0, -5.0, -5.0, 10.0, 10.0, 10.0]
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("eps_growth"), fi)
    assert result["eps_growth"].isna().all()
    assert get_factor_notes(result)["eps_growth"] == FactorNote.NON_POSITIVE_DENOMINATOR


def test_peg_positive_case_reuses_per_and_eps_growth_kernels(idx, clean_valuation):
    clean_valuation["close"] = [120.0] * 6
    clean_valuation["eps"] = [10.0, 10.0, 12.0, 12.0, 12.0, 12.0]
    fi = _fi(idx, clean_valuation)
    per_result = compute_factor(get_factor("per"), fi)
    peg_result = compute_factor(get_factor("peg"), fi)
    # idx=2 시점: per=120/12=10, eps_growth=(12-10)/10=0.2 -> peg = 10 / (0.2*100) = 0.5
    assert peg_result["peg"].iloc[2] == pytest.approx(per_result["per"].iloc[2] / (0.2 * 100))


def test_market_cap_passthrough(idx, clean_valuation):
    fi = _fi(idx, clean_valuation)
    result = compute_factor(get_factor("market_cap"), fi)
    pd.testing.assert_series_equal(
        result["market_cap"], clean_valuation["market_cap"], check_names=False
    )


def test_registry_includes_all_valuation_factor_ids():
    from quant_krx.factors.registry import list_factors

    ids = {f.id for f in list_factors()}
    assert set(VALUATION_IDS) <= ids
