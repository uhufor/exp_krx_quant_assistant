from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal, Protocol, runtime_checkable

import pandas as pd

FundamentalKind = Literal["valuation", "financials"]


@runtime_checkable
class FundamentalProvider(Protocol):
    """밸류에이션·재무제표 조달 계약. OHLCV DataProvider와 분리 정의(FR-16)."""

    def fetch_valuation(
        self, symbols: Sequence[str], start: date, end: date
    ) -> pd.DataFrame: ...

    def fetch_financials(
        self, symbols: Sequence[str], start: date, end: date
    ) -> pd.DataFrame: ...
