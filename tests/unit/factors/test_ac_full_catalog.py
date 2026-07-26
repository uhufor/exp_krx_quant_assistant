from __future__ import annotations

import inspect

import pandas as pd
import pytest

from quant_krx.factors.base import FactorInput
from quant_krx.factors.metadata import FactorCategory
from quant_krx.factors.registry import _REGISTRY, list_factors

# PRD-R01 §4 표 원천 — id -> 기대 카테고리 (AC-R01-01 카테고리 분포 검증)
_EXPECTED_CATEGORY = {
    "price": FactorCategory.PRICE, "sma": FactorCategory.TREND, "ema": FactorCategory.TREND,
    "rsi": FactorCategory.MOMENTUM, "macd": FactorCategory.TREND,
    "bollinger": FactorCategory.VOLATILITY, "momentum": FactorCategory.MOMENTUM,
    "per": FactorCategory.VALUE, "pbr": FactorCategory.VALUE,
    "earnings_yield": FactorCategory.VALUE, "dividend_yield": FactorCategory.VALUE,
    "eps": FactorCategory.QUALITY, "bps": FactorCategory.QUALITY,
    "roe_approx": FactorCategory.QUALITY, "payout_ratio": FactorCategory.QUALITY,
    "eps_growth": FactorCategory.GROWTH, "peg": FactorCategory.GROWTH,
    "market_cap": FactorCategory.SIZE,
    "psr": FactorCategory.VALUE, "pcr": FactorCategory.VALUE,
    "ev_ebitda": FactorCategory.VALUE, "roa": FactorCategory.QUALITY,
    "roic": FactorCategory.QUALITY, "gross_margin": FactorCategory.QUALITY,
    "operating_margin": FactorCategory.QUALITY, "net_margin": FactorCategory.QUALITY,
    "gp_to_assets": FactorCategory.QUALITY, "revenue_growth": FactorCategory.GROWTH,
    "op_income_growth": FactorCategory.GROWTH, "debt_to_equity": FactorCategory.STABILITY,
    "current_ratio": FactorCategory.STABILITY, "interest_coverage": FactorCategory.STABILITY,
    "trading_value": FactorCategory.VOLUME, "volume": FactorCategory.VOLUME,
    "rolling_high": FactorCategory.TREND,
}


def test_ac_r01_01_registry_has_exactly_32_factors_with_no_duplicates():
    factors = list_factors()
    assert len(factors) == 35
    ids = [f.id for f in factors]
    assert len(ids) == len(set(ids))


def test_ac_r01_01_category_distribution_matches_prd_table():
    factors = {f.id: f for f in list_factors()}
    assert set(factors) == set(_EXPECTED_CATEGORY)
    for factor_id, expected_category in _EXPECTED_CATEGORY.items():
        assert factors[factor_id].category == expected_category, (
            f"{factor_id}: expected {expected_category}, got {factors[factor_id].category}"
        )


def test_ac_r01_04_all_non_ohlcv_factors_accept_factor_input():
    """required_data != ('ohlcv',)인 전 등록 팩터가 FactorInput 시그니처와 호환되는지 전수 스캔."""
    idx = pd.date_range("2022-01-01", periods=600, freq="D")
    ohlcv = pd.DataFrame({"close": [100.0] * len(idx)}, index=idx)
    valuation = pd.DataFrame(
        {"close": [100.0] * len(idx), "eps": [10.0] * len(idx), "bps": [50.0] * len(idx),
         "div": [0.01] * len(idx), "dps": [2.0] * len(idx), "market_cap": [1e9] * len(idx),
         "shares": [1e6] * len(idx)},
        index=idx,
    )
    financials = pd.DataFrame([{
        "symbol": "TEST", "fiscal_year": 2023, "fiscal_quarter": 1,
        "statement_scope": "consolidated", "revenue": 1000.0, "gross_profit": 350.0,
        "operating_income": 150.0, "net_income": 100.0, "pretax_income": 130.0,
        "income_tax": 30.0, "total_assets": 5000.0, "total_debt": 1500.0,
        "total_equity": 3500.0, "current_assets": 2000.0, "current_liabilities": 750.0,
        "operating_cash_flow": 160.0, "interest_expense": 10.0,
        "depreciation_amortization": 50.0, "cash_and_equivalents": 500.0,
        "invested_capital": 5000.0, "period_end": pd.Timestamp("2023-03-31"),
        "disclosure_date": pd.Timestamp("2023-05-15"),
    }])
    fi = FactorInput(ohlcv=ohlcv, valuation=valuation, financials=financials)

    scanned = 0
    for factor_id, constructor in _REGISTRY.items():
        instance = constructor()
        if instance.metadata.required_data == ("ohlcv",):
            continue
        scanned += 1
        sig = inspect.signature(instance.compute)
        assert "data" in sig.parameters, f"{factor_id}.compute은 data 파라미터를 가져야 함"
        result = instance.compute(fi)  # FactorInput 호환성 실제 호출로 검증
        assert isinstance(result, pd.DataFrame), f"{factor_id}.compute은 DataFrame을 반환해야 함"
    assert scanned == 25, "밸류에이션 11 + 재무제표 14 = 25종이 FactorInput 분기여야 함"


@pytest.mark.parametrize("factor_id", sorted(_EXPECTED_CATEGORY))
def test_ac_r01_03_paramspec_default_matches_constructor_for_every_factor(factor_id):
    constructor = _REGISTRY[factor_id]
    instance = constructor()
    sig = inspect.signature(constructor)
    for spec in instance.metadata.params:
        assert spec.default == sig.parameters[spec.name].default
