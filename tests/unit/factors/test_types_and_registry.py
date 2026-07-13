from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from quant_krx.factors.base import Factor, FactorInput
from quant_krx.factors.dispatch import compute_factor
from quant_krx.factors.errors import (
    DuplicateFactorError,
    ParamValidationError,
    UnknownFactorError,
)
from quant_krx.factors.metadata import FactorCategory, FactorMetadata, ParamSpec
from quant_krx.factors.registry import (
    _METADATA,
    _REGISTRY,
    get_factor,
    list_factors,
    register_factor,
)


def test_factor_category_has_11_values():
    assert {c.value for c in FactorCategory} == {
        "price", "trend", "momentum", "volatility", "mean_reversion",
        "volume", "value", "quality", "growth", "stability", "size",
    }


def test_paramspec_and_metadata_are_frozen():
    spec = ParamSpec("window", int, 20, "desc", min=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.default = 10  # type: ignore[misc]

    meta = FactorMetadata(id="x", display_name="X", category=FactorCategory.TREND, description="d")
    with pytest.raises(dataclasses.FrozenInstanceError):
        meta.id = "y"  # type: ignore[misc]


def test_factor_input_is_frozen_and_optional_fields_default_none():
    fi = FactorInput(ohlcv=pd.DataFrame())
    assert fi.valuation is None
    assert fi.financials is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        fi.ohlcv = pd.DataFrame()  # type: ignore[misc]


class _StubOhlcvFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="_stub_ohlcv",
            display_name="Stub",
            category=FactorCategory.PRICE,
            description="test stub",
            output=("value",),
            required_data=("ohlcv",),
        )

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        result = pd.DataFrame({"value": data["close"]}, index=data.index)
        return result


class _StubFactorInputFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="_stub_fi",
            display_name="Stub FI",
            category=FactorCategory.VALUE,
            description="test stub",
            output=("value",),
            required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        assert isinstance(data, FactorInput)
        result = pd.DataFrame({"value": [1.0]})
        result.attrs["notes"] = {"value": "sentinel"}
        return result


def test_stub_factors_satisfy_factor_protocol_via_duck_typing():
    assert isinstance(_StubOhlcvFactor(), Factor)
    assert isinstance(_StubFactorInputFactor(), Factor)


def test_dispatch_routes_ohlcv_vs_factor_input_by_required_data():
    ohlcv = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    result = compute_factor(_StubOhlcvFactor(), ohlcv)
    assert list(result.columns) == ["value"]

    result2 = compute_factor(_StubFactorInputFactor(), FactorInput(ohlcv=ohlcv))
    assert result2.attrs["notes"] == {"value": "sentinel"}, (
        "attrs['notes']는 디스패치 경계를 그대로 통과해야 함"
    )


def test_dispatch_promotes_bare_dataframe_to_factor_input():
    ohlcv = pd.DataFrame({"close": [1.0, 2.0]})
    # required_data=("ohlcv",)인 스텁은 bare DataFrame을 그대로 받아도 동작해야 함
    result = compute_factor(_StubOhlcvFactor(), ohlcv)
    assert result["value"].tolist() == [1.0, 2.0]


def test_register_factor_rejects_duplicate_id():
    class _DupFactor(_StubOhlcvFactor):
        @property
        def metadata(self) -> FactorMetadata:
            return dataclasses.replace(super().metadata, id="_dup_test")

    register_factor("_dup_test", _DupFactor)
    try:
        with pytest.raises(DuplicateFactorError):
            register_factor("_dup_test", _DupFactor)
    finally:
        _REGISTRY.pop("_dup_test", None)
        _METADATA.pop("_dup_test", None)


def test_get_factor_unknown_id_lists_available_ids():
    with pytest.raises(UnknownFactorError) as exc_info:
        get_factor("_definitely_not_registered")
    assert "_definitely_not_registered" in str(exc_info.value)


def test_get_factor_rejects_unknown_param_key():
    with pytest.raises(ParamValidationError):
        get_factor("sma", not_a_real_param=1)


def test_get_factor_rejects_out_of_range_param():
    with pytest.raises(ParamValidationError):
        get_factor("bollinger", window=1)  # min=2


def test_list_factors_filters_by_category():
    all_factors = list_factors()
    trend_factors = list_factors(FactorCategory.TREND)
    assert len(trend_factors) <= len(all_factors)
    assert all(f.category == FactorCategory.TREND for f in trend_factors)


def test_list_factors_is_sorted_by_id():
    ids = [f.id for f in list_factors()]
    assert ids == sorted(ids)
