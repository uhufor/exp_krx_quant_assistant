from __future__ import annotations

import pandas as pd

from .base import Factor, FactorInput


def compute_factor(factor: Factor, data: FactorInput | pd.DataFrame) -> pd.DataFrame:
    """팩터 계산 유일 인가 디스패치 (DESIGN-R01 §3.6).

    호출자는 factor.compute()를 직접 호출하지 않고 반드시 본 함수를 통해서만 계산한다.
    """
    if isinstance(data, pd.DataFrame):
        data = FactorInput(ohlcv=data)

    if factor.metadata.required_data == ("ohlcv",):
        return factor.compute(data.ohlcv)
    return factor.compute(data)
