from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from quant_krx.workspace.numeric import align, binary_arith, broadcast, compare, crosses

INDEX = pd.date_range("2024-01-01", periods=5, freq="D")


def test_align_extends_with_nan_no_interpolation() -> None:
    series = pd.Series([1.0, 2.0], index=INDEX[:2])
    result = align(series, INDEX)
    assert result.iloc[0] == 1.0
    assert result.iloc[1] == 2.0
    assert result.iloc[2:].isna().all()


def test_broadcast_produces_constant_series() -> None:
    result = broadcast(5.0, INDEX)
    assert (result == 5.0).all()
    assert list(result.index) == list(INDEX)


def test_binary_arith_add_sub_mul() -> None:
    left = pd.Series([1.0, 2.0, 3.0], index=INDEX[:3])
    right = pd.Series([1.0, 1.0, 1.0], index=INDEX[:3])
    assert_series_equal(binary_arith("+", left, right), left + right)
    assert_series_equal(binary_arith("-", left, right), left - right)
    assert_series_equal(binary_arith("*", left, right), left * right)


def test_binary_arith_div_by_zero_is_nan_no_exception() -> None:
    left = pd.Series([1.0, 2.0, 3.0], index=INDEX[:3])
    right = pd.Series([1.0, 0.0, 2.0], index=INDEX[:3])
    result = binary_arith("/", left, right)
    assert result.iloc[0] == 1.0
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == 1.5


def test_binary_arith_unknown_op_rejected() -> None:
    left = pd.Series([1.0], index=INDEX[:1])
    with pytest.raises(ValueError):
        binary_arith("%", left, left)


def test_compare_nan_input_forced_false() -> None:
    left = pd.Series([1.0, np.nan, 3.0], index=INDEX[:3])
    right = pd.Series([0.0, 0.0, 0.0], index=INDEX[:3])
    result = compare(">", left, right)
    assert result.tolist() == [True, False, True]
    assert result.dtype == bool


def test_compare_all_operators_match_pandas_reference() -> None:
    left = pd.Series([1.0, 2.0, 3.0], index=INDEX[:3])
    right = pd.Series([2.0, 2.0, 2.0], index=INDEX[:3])
    for op, expected in [
        (">", left > right), (">=", left >= right),
        ("<", left < right), ("<=", left <= right),
        ("==", left == right), ("!=", left != right),
    ]:
        result = compare(op, left, right)
        assert result.tolist() == expected.tolist()


def test_compare_unknown_op_rejected() -> None:
    left = pd.Series([1.0], index=INDEX[:1])
    with pytest.raises(ValueError):
        compare("~=", left, left)


def test_crosses_above_matches_manual_pandas_derivation() -> None:
    left = pd.Series([1.0, 3.0, 2.0, 5.0, 1.0], index=INDEX)
    right = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0], index=INDEX)
    expected = (left > right) & (left.shift(1) <= right.shift(1))
    expected.iloc[0] = False  # shift 첫 원소는 NaN 비교 → False
    result = crosses("crosses_above", left, right)
    assert result.tolist() == expected.tolist()
    assert result.iloc[0] == False  # noqa: E712


def test_crosses_below_symmetric() -> None:
    left = pd.Series([3.0, 1.0, 2.0, -1.0, 3.0], index=INDEX)
    right = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0], index=INDEX)
    expected = (left < right) & (left.shift(1) >= right.shift(1))
    expected.iloc[0] = False
    result = crosses("crosses_below", left, right)
    assert result.tolist() == expected.tolist()


def test_crosses_with_scalar_broadcast_does_not_crash() -> None:
    left = pd.Series([1.0, 3.0, 2.0], index=INDEX[:3])
    right = broadcast(2.0, INDEX[:3])
    result = crosses("crosses_above", left, right)
    assert result.dtype == bool


def test_crosses_unknown_direction_rejected() -> None:
    left = pd.Series([1.0], index=INDEX[:1])
    with pytest.raises(ValueError):
        crosses("crosses_sideways", left, left)


def test_deterministic_two_calls_identical() -> None:
    left = pd.Series([1.0, 3.0, 2.0, 5.0, 1.0], index=INDEX)
    right = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0], index=INDEX)
    assert_series_equal(compare(">", left, right), compare(">", left, right))
    assert_series_equal(
        crosses("crosses_above", left, right), crosses("crosses_above", left, right)
    )
    assert_series_equal(binary_arith("/", left, right), binary_arith("/", left, right))
