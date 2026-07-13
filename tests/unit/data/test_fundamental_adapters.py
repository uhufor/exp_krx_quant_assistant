from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.data.dart_fundamental import DartFundamentalAdapter
from quant_krx.data.pykrx_fundamental import PyKrxFundamentalAdapter


def test_pykrx_merge_valuation_shapes_columns_correctly():
    fundamental = pd.DataFrame(
        {"BPS": [46000.0], "PER": [10.0], "PBR": [1.5], "EPS": [7000.0],
         "DIV": [0.02], "DPS": [1400.0]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    cap = pd.DataFrame(
        {"시가총액": [1e12], "거래량": [1000], "거래대금": [1e8], "상장주식수": [1e7]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    ohlcv = pd.DataFrame(
        {"시가": [69000.0], "고가": [70000.0], "저가": [68500.0], "종가": [70000.0],
         "거래량": [1000]},
        index=pd.to_datetime(["2024-01-02"]),
    )

    merged = PyKrxFundamentalAdapter._merge_valuation("005930", fundamental, cap, ohlcv)

    assert set(merged.columns) == {
        "symbol", "date", "close", "per", "pbr", "eps", "bps", "div", "dps",
        "market_cap", "shares",
    }
    assert merged["symbol"].iloc[0] == "005930"
    assert merged["close"].iloc[0] == 70000.0
    assert merged["market_cap"].iloc[0] == 1e12


def test_pykrx_fetch_financials_raises_not_implemented():
    adapter = PyKrxFundamentalAdapter()
    with pytest.raises(NotImplementedError, match="재무제표"):
        adapter.fetch_financials(["005930"], date(2024, 1, 1), date(2024, 1, 31))


def test_dart_adapter_raises_not_implemented_for_both_methods():
    adapter = DartFundamentalAdapter()
    with pytest.raises(NotImplementedError, match="Deferred"):
        adapter.fetch_valuation(["005930"], date(2024, 1, 1), date(2024, 1, 31))
    with pytest.raises(NotImplementedError, match="Deferred"):
        adapter.fetch_financials(["005930"], date(2024, 1, 1), date(2024, 1, 31))
