from datetime import date

import pandas as pd
import pytest

from quant_krx.storage.validation import DataValidator


@pytest.fixture
def validator():
    return DataValidator()


@pytest.fixture
def good_df():
    dates = pd.bdate_range("2024-01-02", periods=20)
    return pd.DataFrame({
        "date": [d.date() for d in dates],
        "close": [50000.0 + i * 100 for i in range(20)],
        "volume": [1000000] * 20,
    })


def test_valid_data(validator, good_df):
    result = validator.validate("005930", good_df)
    assert result.ok
    assert result.issues == []
    assert result.row_count == 20


def test_empty_df(validator):
    result = validator.validate("005930", pd.DataFrame())
    assert not result.ok
    assert any("Empty" in i for i in result.issues)


def test_nonpositive_close(validator, good_df):
    bad = good_df.copy()
    bad.loc[0, "close"] = -1.0
    result = validator.validate("005930", bad)
    assert not result.ok
    assert any("Non-positive" in i for i in result.issues)


def test_duplicate_dates(validator, good_df):
    dup = pd.concat([good_df, good_df.iloc[:1]], ignore_index=True)
    result = validator.validate("005930", dup)
    assert not result.ok
    assert any("Duplicate" in i for i in result.issues)


def test_stale_data_warning(validator, good_df):
    result = validator.validate("005930", good_df, as_of=date(2025, 1, 1))
    assert result.ok  # 이슈는 없지만
    assert any("Stale" in w for w in result.warnings)
