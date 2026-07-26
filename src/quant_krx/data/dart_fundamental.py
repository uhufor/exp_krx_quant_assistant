from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date, datetime

import httpx
import pandas as pd

from .dart_account_mapping import extract_financial_fields
from .dart_corp_code import DartCorpCodeResolver

_FNLTT_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

# reprt_code → (fiscal_quarter, period_end의 월-일) — TR-R01-D03, TRD-R01-D §4
_REPRT_CODE_TO_QUARTER: dict[str, tuple[int, str]] = {
    "11013": (1, "-03-31"),
    "11012": (2, "-06-30"),
    "11014": (3, "-09-30"),
    "11011": (4, "-12-31"),
}

_FINANCIALS_VALUE_COLUMNS = (
    "revenue", "gross_profit", "operating_income", "net_income", "pretax_income",
    "income_tax", "total_assets", "total_debt", "total_equity", "current_assets",
    "current_liabilities", "operating_cash_flow", "interest_expense",
    "depreciation_amortization", "cash_and_equivalents", "invested_capital",
)

_FINANCIALS_COLUMNS = (
    "symbol", "fiscal_year", "fiscal_quarter", "statement_scope",
    *_FINANCIALS_VALUE_COLUMNS,
    "period_end", "disclosure_date",
)


class DartFundamentalAdapter:
    """DART Open API 기반 재무제표 어댑터 (TRD-R01-D — TR-R01-D01~D04 확정 반영).

    밸류에이션(PER/PBR/시가총액 등)은 DART가 제공하지 않는 시장 데이터이므로
    fetch_valuation은 지원하지 않는다 — 밸류에이션은 PyKrxFundamentalAdapter를 사용한다.
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        corp_code_resolver: DartCorpCodeResolver | None = None,
    ) -> None:
        api_key = os.getenv("DART_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DART 재무제표 조회에는 opendart.fss.or.kr 발급 인증키가 필요합니다. "
                "환경변수 DART_API_KEY를 설정하세요."
            )
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None
        self._corp_code_resolver = corp_code_resolver or DartCorpCodeResolver(
            api_key, client=self._client
        )

    @property
    def source_name(self) -> str:
        return "DART"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_valuation(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        raise NotImplementedError(
            "DartFundamentalAdapter는 밸류에이션(PER/PBR/시가총액)을 지원하지 않습니다. "
            "밸류에이션 수집은 PyKrxFundamentalAdapter를 사용하십시오."
        )

    def fetch_financials(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        corp_codes = self._corp_code_resolver.resolve(symbols)
        rows: list[dict] = []
        for symbol, corp_code in corp_codes.items():
            for bsns_year in range(start.year, end.year + 1):
                for reprt_code in _REPRT_CODE_TO_QUARTER:
                    row = self._fetch_one_period(symbol, corp_code, bsns_year, reprt_code)
                    if row is not None and start <= row["disclosure_date"] <= end:
                        rows.append(row)

        if not rows:
            return pd.DataFrame(columns=list(_FINANCIALS_COLUMNS))
        return pd.DataFrame(rows)[list(_FINANCIALS_COLUMNS)]

    def _fetch_one_period(
        self, symbol: str, corp_code: str, bsns_year: int, reprt_code: str
    ) -> dict | None:
        # 연결(CFS) 우선 → 별도(OFS) 폴백 (TR-R01-D04, TRD-R01-D §5)
        for fs_div, scope in (("CFS", "consolidated"), ("OFS", "separate")):
            records = self._call_api(corp_code, bsns_year, reprt_code, fs_div)
            if records is not None:
                return self._build_row(symbol, bsns_year, reprt_code, scope, records)
        return None

    def _call_api(
        self, corp_code: str, bsns_year: int, reprt_code: str, fs_div: str
    ) -> pd.DataFrame | None:
        response = self._client.get(
            _FNLTT_URL,
            params={
                "crtfc_key": self._api_key,
                "corp_code": corp_code,
                "bsns_year": str(bsns_year),
                "reprt_code": reprt_code,
                "fs_div": fs_div,
            },
        )
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status")
        if status == "013":
            return None  # 데이터 없음 — CFS/OFS 폴백 또는 결측 처리 대상(하드 실패 아님)
        if status != "000":
            raise RuntimeError(
                f"DART fnlttSinglAcntAll 요청 실패 (status={status}): {payload.get('message', '')}"
            )
        return pd.DataFrame(payload.get("list", []))

    def _build_row(
        self,
        symbol: str,
        bsns_year: int,
        reprt_code: str,
        statement_scope: str,
        records: pd.DataFrame,
    ) -> dict:
        fiscal_quarter, month_day = _REPRT_CODE_TO_QUARTER[reprt_code]
        row: dict = {
            "symbol": symbol,
            "fiscal_year": bsns_year,
            "fiscal_quarter": fiscal_quarter,
            "statement_scope": statement_scope,
            "period_end": date.fromisoformat(f"{bsns_year}{month_day}"),
            "disclosure_date": _extract_disclosure_date(records),
        }
        fields = extract_financial_fields(records)
        for column in _FINANCIALS_VALUE_COLUMNS:
            row[column] = fields.get(column, float("nan"))
        return row


def _extract_disclosure_date(records: pd.DataFrame) -> date:
    # rcept_no(14자리) 앞 8자리가 접수일자(YYYYMMDD) — TR-R01-D03, TRD-R01-D §4
    rcept_no = str(records["rcept_no"].iloc[0])
    return datetime.strptime(rcept_no[:8], "%Y%m%d").date()
