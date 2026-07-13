from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd

_NOT_IMPLEMENTED_MESSAGE = (
    "DartFundamentalAdapter는 아직 구현되지 않았습니다(Phase F2-b, Deferred). "
    "선행 명세(corp_code 해결, account_nm 매핑, disclosure_date/period_end 추출 규약, "
    "연결/별도 폴백 정책) 확정 후 착수 예정입니다. 재무제표 오프라인 검증은 "
    "FixtureFundamentalAdapter를 사용하십시오."
)


class DartFundamentalAdapter:
    """DART Open API 기반 재무제표 어댑터. TR-R01-D01~D04 선행 명세 확정 전까지 미구현(Deferred)."""

    @property
    def source_name(self) -> str:
        return "DART"

    def fetch_valuation(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)

    def fetch_financials(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)
