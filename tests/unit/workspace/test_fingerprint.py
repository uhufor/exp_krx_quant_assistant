from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.factors import FactorInput
from quant_krx.workspace.fingerprint import (
    cache_key,
    coverage_fingerprint,
    definition_fingerprint,
    params_fingerprint,
)


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes, "high": closes, "low": closes,
            "close": closes, "volume": [100.0] * len(closes),
        },
        index=index,
    )


def _factor_input(closes: list[float]) -> FactorInput:
    return FactorInput(ohlcv=_ohlcv(closes), valuation=None, financials=None)


def test_definition_fingerprint_is_key_order_independent():
    # 같은 내용이면 딕셔너리 키 순서가 달라도 같은 지문이어야 한다(정규 직렬화).
    a = {"strategy": {"id": "s1", "name": "n"}, "rules": [], "formulas": []}
    b = {"formulas": [], "rules": [], "strategy": {"name": "n", "id": "s1"}}
    assert definition_fingerprint(a) == definition_fingerprint(b)


def test_definition_fingerprint_changes_when_referenced_rule_changes():
    # 전략 본문이 같아도 전이 참조 Rule이 바뀌면 결과가 달라지므로 지문도 달라야 한다.
    base = {"strategy": {"id": "s1"}, "rules": [{"id": "r1", "op": ">"}], "formulas": []}
    changed = {"strategy": {"id": "s1"}, "rules": [{"id": "r1", "op": "<"}], "formulas": []}
    assert definition_fingerprint(base) != definition_fingerprint(changed)


@pytest.mark.parametrize(
    "overrides",
    [
        {"fees": 0.005},
        {"slippage": 0.002},
        {"data_source": "krx_dart"},
        {"benchmark": "KOSDAQ"},
        {"start": date(2023, 1, 1)},
        {"end": date(2025, 1, 1)},
        {"symbols": ["005930", "000660"]},
    ],
)
def test_params_fingerprint_changes_for_each_parameter(overrides):
    baseline = {
        "symbols": ["005930"], "start": date(2024, 1, 1), "end": date(2024, 12, 31),
        "fees": 0.003, "slippage": 0.001, "data_source": "fixture", "benchmark": "KOSPI",
    }
    assert params_fingerprint(**baseline) != params_fingerprint(**{**baseline, **overrides})


def test_params_fingerprint_preserves_symbol_order():
    # symbols 순서는 대표 종목 선정에 영향을 주므로 정렬해 뭉개면 안 된다.
    common = {
        "start": None, "end": None, "fees": 0.003, "slippage": 0.001,
        "data_source": "fixture", "benchmark": None,
    }
    first = params_fingerprint(symbols=["005930", "000660"], **common)
    second = params_fingerprint(symbols=["000660", "005930"], **common)
    assert first != second


def test_coverage_fingerprint_is_stable_for_identical_data():
    a = {"005930": _factor_input([100.0, 101.0, 102.0])}
    b = {"005930": _factor_input([100.0, 101.0, 102.0])}
    assert coverage_fingerprint(a) == coverage_fingerprint(b)


def test_coverage_fingerprint_detects_appended_rows():
    base = {"005930": _factor_input([100.0, 101.0])}
    extended = {"005930": _factor_input([100.0, 101.0, 102.0])}
    assert coverage_fingerprint(base) != coverage_fingerprint(extended)


def test_coverage_fingerprint_detects_corrected_past_value():
    """정정공시처럼 과거 구간 값만 바뀌는 경우 — 행 수·마지막 날짜는 그대로다.

    요약 통계 기반 지문이었다면 이 변화를 놓쳐 낡은 결과를 캐시 히트로 돌려주게 된다.
    """
    base = {"005930": _factor_input([100.0, 101.0, 102.0])}
    corrected = {"005930": _factor_input([100.0, 999.0, 102.0])}
    assert coverage_fingerprint(base) != coverage_fingerprint(corrected)


def test_coverage_fingerprint_detects_benchmark_change():
    data = {"005930": _factor_input([100.0, 101.0])}
    assert coverage_fingerprint(data, _ohlcv([50.0, 51.0])) != coverage_fingerprint(
        data, _ohlcv([50.0, 52.0])
    )


def test_coverage_fingerprint_detects_fundamental_change():
    index = pd.date_range("2024-01-01", periods=2, freq="D")
    left = FactorInput(
        ohlcv=_ohlcv([100.0, 101.0]),
        valuation=pd.DataFrame({"per": [10.0, 11.0]}, index=index),
        financials=None,
    )
    right = FactorInput(
        ohlcv=_ohlcv([100.0, 101.0]),
        valuation=pd.DataFrame({"per": [10.0, 12.0]}, index=index),
        financials=None,
    )
    assert coverage_fingerprint({"A": left}) != coverage_fingerprint({"A": right})


def test_cache_key_combines_all_three_axes():
    base = cache_key("def", "params", "coverage")
    assert base != cache_key("def2", "params", "coverage")
    assert base != cache_key("def", "params2", "coverage")
    assert base != cache_key("def", "params", "coverage2")
    assert base == cache_key("def", "params", "coverage")
