from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_krx.factors.dispatch import compute_factor
from quant_krx.factors.registry import get_factor

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sample_ohlcv.csv"


@pytest.fixture(scope="module")
def ohlcv() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE_PATH, dtype={"symbol": str}, parse_dates=["date"])
    df = df[df["symbol"] == "005930"].sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


TECHNICAL_IDS = ["price", "sma", "ema", "rsi", "macd", "bollinger", "momentum"]


@pytest.mark.parametrize("factor_id", TECHNICAL_IDS)
def test_determinism_two_calls_equal(ohlcv, factor_id):
    factor = get_factor(factor_id)
    r1 = compute_factor(factor, ohlcv)
    r2 = compute_factor(factor, ohlcv)
    pd.testing.assert_frame_equal(r1, r2)


@pytest.mark.parametrize("factor_id", TECHNICAL_IDS)
def test_input_not_mutated(ohlcv, factor_id):
    before = ohlcv.copy(deep=True)
    factor = get_factor(factor_id)
    compute_factor(factor, ohlcv)
    pd.testing.assert_frame_equal(ohlcv, before)


@pytest.mark.parametrize("factor_id", TECHNICAL_IDS)
def test_output_columns_match_metadata(ohlcv, factor_id):
    factor = get_factor(factor_id)
    result = compute_factor(factor, ohlcv)
    assert set(result.columns) == set(factor.metadata.output)
    assert result.index.equals(ohlcv.index)


def test_price_is_close_passthrough(ohlcv):
    factor = get_factor("price")
    result = compute_factor(factor, ohlcv)
    pd.testing.assert_series_equal(result["close"], ohlcv["close"], check_names=False)


def test_sma_parity_reraived_independently(ohlcv):
    factor = get_factor("sma", window=10)
    result = compute_factor(factor, ohlcv)
    expected = ohlcv["close"].rolling(10).mean()
    pd.testing.assert_series_equal(result["sma"], expected, check_names=False)
    assert result["sma"].iloc[:9].isna().all()


def test_ema_parity(ohlcv):
    factor = get_factor("ema", span=10)
    result = compute_factor(factor, ohlcv)
    expected = ohlcv["close"].ewm(span=10, adjust=False).mean()
    pd.testing.assert_series_equal(result["ema"], expected, check_names=False)


def test_rsi_parity(ohlcv):
    factor = get_factor("rsi", window=14)
    result = compute_factor(factor, ohlcv)
    delta = ohlcv["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    expected = 100 - 100 / (1 + rs)
    pd.testing.assert_series_equal(result["rsi"], expected, check_names=False)


def test_macd_parity(ohlcv):
    factor = get_factor("macd", fast=12, slow=26, signal=9)
    result = compute_factor(factor, ohlcv)
    ema_fast = ohlcv["close"].ewm(span=12, adjust=False).mean()
    ema_slow = ohlcv["close"].ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    pd.testing.assert_series_equal(result["macd"], macd, check_names=False)
    pd.testing.assert_series_equal(result["signal"], signal, check_names=False)


def test_bollinger_parity(ohlcv):
    factor = get_factor("bollinger", window=20, num_std=2.0)
    result = compute_factor(factor, ohlcv)
    middle = ohlcv["close"].rolling(20).mean()
    std = ohlcv["close"].rolling(20).std(ddof=1)
    pd.testing.assert_series_equal(result["middle"], middle, check_names=False)
    pd.testing.assert_series_equal(result["upper"], middle + 2.0 * std, check_names=False)
    pd.testing.assert_series_equal(result["lower"], middle - 2.0 * std, check_names=False)


def test_momentum_parity(ohlcv):
    factor = get_factor("momentum", lookback=60, skip=5)
    result = compute_factor(factor, ohlcv)
    expected = ohlcv["close"].shift(5) / ohlcv["close"].shift(60) - 1
    pd.testing.assert_series_equal(result["momentum"], expected, check_names=False)
    assert result["momentum"].notna().any(), (
        "momentum이 전 구간 NaN이면 안 됨(lookback 축소로 비-NaN 구간 확보)"
    )


def test_sma_different_params_are_independent(ohlcv):
    r5 = compute_factor(get_factor("sma", window=5), ohlcv)
    r20 = compute_factor(get_factor("sma", window=20), ohlcv)
    assert not r5["sma"].equals(r20["sma"])


def test_macd_cross_constraint_rejects_fast_gte_slow():
    from quant_krx.factors.errors import ParamValidationError

    with pytest.raises(ParamValidationError):
        get_factor("macd", fast=26, slow=12)


def test_bollinger_window_below_min_rejected():
    from quant_krx.factors.errors import ParamValidationError

    with pytest.raises(ParamValidationError):
        get_factor("bollinger", window=1)


def test_paramspec_default_matches_constructor_default_for_all_technical_factors():
    import inspect

    from quant_krx.factors.registry import _REGISTRY

    for factor_id in TECHNICAL_IDS:
        constructor = _REGISTRY[factor_id]
        instance = constructor()
        sig = inspect.signature(constructor)
        for spec in instance.metadata.params:
            ctor_default = sig.parameters[spec.name].default
            assert spec.default == ctor_default, (
                f"{factor_id}.{spec.name}: ParamSpec.default({spec.default}) != "
                f"생성자 기본값({ctor_default})"
            )
