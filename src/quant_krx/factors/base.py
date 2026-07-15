from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from .metadata import FactorMetadata


@dataclass(frozen=True)
class FactorInput:
    """단일 종목 팩터 계산 입력 번들 (DESIGN-R01 §3.4).

    ohlcv: 오름차순 DatetimeIndex, 컬럼 open/high/low/close/volume (수정주가)
    valuation: 오름차순 DatetimeIndex(= ohlcv 캘린더),
        컬럼 close/per/pbr/eps/bps/div/dps/market_cap/shares
    financials: disclosure_date 오름차순 RangeIndex(원본, as-of 미정렬),
        계정 컬럼 + period_end/disclosure_date/fiscal_year/fiscal_quarter/statement_scope
    """

    ohlcv: pd.DataFrame
    valuation: pd.DataFrame | None = None
    financials: pd.DataFrame | None = None


@runtime_checkable
class Factor(Protocol):
    @property
    def metadata(self) -> FactorMetadata: ...

    def compute(self, data: pd.DataFrame | FactorInput) -> pd.DataFrame: ...

    # 선택적 훅 validate_params(params) -> tuple[str, ...] (§3.3): 교차 파라미터 제약이
    # 있는 팩터만 구현한다. runtime_checkable isinstance 판정에 강제되지 않도록 Protocol
    # 멤버에서 제외하고, 호출부(registry.get_factor)는 getattr(factor, "validate_params",
    # None)로 유무를 판정한다.
