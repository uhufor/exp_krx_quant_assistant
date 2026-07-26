from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta

import httpx
import pandas as pd

from .dart_account_mapping import extract_financial_fields
from .dart_corp_code import DartCorpCodeResolver
from .dart_missing_period_cache import DartMissingPeriodCache

_FNLTT_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

# reprt_code → (fiscal_quarter, period_end의 월-일) — TR-R01-D03, TRD-R01-D §4
_REPRT_CODE_TO_QUARTER: dict[str, tuple[int, str]] = {
    "11013": (1, "-03-31"),
    "11012": (2, "-06-30"),
    "11014": (3, "-09-30"),
    "11011": (4, "-12-31"),
}

# 연중 분기 순서(오름차순) — 최신 분기 후보 역순 탐색(fetch_latest_financials)에 사용.
_QUARTER_ORDER = ("11013", "11012", "11014", "11011")

# 사업보고서(90일) 유예에 여유를 더한 보수적 상수 — 분기의 period_end가 이보다 오래전이면
# 최악의 경우도 이미 공시 마감됐을 것으로 보고 범위 밖(TRD-R04 후속 버그 수정 §1) 판정에 쓴다.
# screening/fundamental_sync.py의 신선도 판정도 동일 상수를 공유한다(중복 정의 금지).
DISCLOSURE_GRACE_DAYS = 100

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
        missing_cache: DartMissingPeriodCache | None = None,
        now_fn: Callable[[], datetime] = datetime.utcnow,
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
        self._missing_cache = missing_cache or DartMissingPeriodCache()
        self._now_fn = now_fn

    @property
    def source_name(self) -> str:
        return "DART"

    def close(self) -> None:
        self._missing_cache.flush()
        if self._owns_client:
            self._client.close()

    def fetch_valuation(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        raise NotImplementedError(
            "DartFundamentalAdapter는 밸류에이션(PER/PBR/시가총액)을 지원하지 않습니다. "
            "밸류에이션 수집은 PyKrxFundamentalAdapter를 사용하십시오."
        )

    def fetch_financials(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        *,
        skip_periods: Mapping[str, set[tuple[int, int]]] | None = None,
    ) -> pd.DataFrame:
        """`skip_periods`(symbol → {(fiscal_year, fiscal_quarter), ...})에 있는 분기는
        이미 DB에 확보된 것으로 보고 DART 호출 자체를 건너뛴다(증분 수집, TRD-R04 §1) —
        호출부가 기존 커버리지를 조회해 넘기며, 없으면(None) 항상 전체 재수집한다(하위 호환).
        """
        corp_codes = self._corp_code_resolver.resolve(symbols)
        rows: list[dict] = []
        for symbol, corp_code in corp_codes.items():
            already = (skip_periods or {}).get(symbol, set())
            for bsns_year in range(start.year, end.year + 1):
                for reprt_code, (fiscal_quarter, _) in _REPRT_CODE_TO_QUARTER.items():
                    if (bsns_year, fiscal_quarter) in already:
                        continue
                    if not _worth_attempting(bsns_year, reprt_code, start, end):
                        continue  # 계산만으로 범위 밖이 확실 — API 호출 없이 생략(버그 수정)
                    row = self._fetch_one_period(symbol, corp_code, bsns_year, reprt_code)
                    if row is not None and start <= row["disclosure_date"] <= end:
                        rows.append(row)

        if not rows:
            return pd.DataFrame(columns=list(_FINANCIALS_COLUMNS))
        return pd.DataFrame(rows)[list(_FINANCIALS_COLUMNS)]

    def fetch_latest_financials(
        self,
        symbols: Sequence[str],
        as_of: date,
        *,
        max_quarters_back: int = 3,
        skip_periods: Mapping[str, set[tuple[int, int]]] | None = None,
    ) -> pd.DataFrame:
        """전종목 순위/스크리닝 전용 — 시계열 백필 없이 종목당 "현재 시점 최신 확정 분기"
        하나만 확보한다(TRD-R04 §2). `as_of` 기준 최근 분기부터 최대 `max_quarters_back`개
        후보를 역순으로 시도하다 첫 성공(CFS 또는 OFS)에서 멈춘다 — `fetch_financials`처럼
        연도 전체를 순회하지 않으므로 종목당 호출 수가 훨씬 적다(평균 1~2회).

        `skip_periods`에 있는 분기를 만나면 그 분기(및 이론상 이보다 오래된 분기)는 이미
        DB에 있다고 보고 즉시 순회를 중단한다 — 최신 분기부터 내려가는 순서라 "이미 있는
        분기에 도달 = 더 볼 필요 없음"이 성립한다.
        """
        corp_codes = self._corp_code_resolver.resolve(symbols)
        candidates = _recent_quarter_candidates(as_of, max_quarters_back)
        rows: list[dict] = []
        for symbol, corp_code in corp_codes.items():
            already = (skip_periods or {}).get(symbol, set())
            for bsns_year, reprt_code in candidates:
                fiscal_quarter = _REPRT_CODE_TO_QUARTER[reprt_code][0]
                if (bsns_year, fiscal_quarter) in already:
                    break
                row = self._fetch_one_period(symbol, corp_code, bsns_year, reprt_code)
                if row is not None:
                    rows.append(row)
                    break

        if not rows:
            return pd.DataFrame(columns=list(_FINANCIALS_COLUMNS))
        return pd.DataFrame(rows)[list(_FINANCIALS_COLUMNS)]

    def _fetch_one_period(
        self, symbol: str, corp_code: str, bsns_year: int, reprt_code: str
    ) -> dict | None:
        fiscal_quarter = _REPRT_CODE_TO_QUARTER[reprt_code][0]
        now = self._now_fn()
        if self._missing_cache.is_recently_checked(symbol, bsns_year, fiscal_quarter, now=now):
            return None  # 최근(TTL 이내)에 "아직 없음"을 확인함 — 재확인 생략(TRD-R04 후속)

        # 연결(CFS) 우선 → 별도(OFS) 폴백 (TR-R01-D04, TRD-R01-D §5)
        for fs_div, scope in (("CFS", "consolidated"), ("OFS", "separate")):
            records = self._call_api(corp_code, bsns_year, reprt_code, fs_div)
            if records is not None:
                return self._build_row(symbol, bsns_year, reprt_code, scope, records)

        self._missing_cache.record_missing(symbol, bsns_year, fiscal_quarter, now=now)
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


def _worth_attempting(bsns_year: int, reprt_code: str, start: date, end: date) -> bool:
    """분기가 `[start, end]` 안에서 공시될 가능성이 조금이라도 있는지 계산만으로 판정한다
    (API 호출 없이) — TRD-R04 후속 버그 수정 §1: 범위 밖이 확실한 분기를 매번 호출한 뒤
    응답을 버리던 문제(호출 결과가 저장 안 되니 다음 실행에서도 또 호출됨)를 해결한다.

    두 조건 모두 계산만으로 판정 가능하다:
    - period_end가 end보다 미래면 분기 자체가 아직 안 끝났으니 공시될 수 없다.
    - period_end + 유예기간(최악 시나리오)이 start보다 이전이면 공시됐더라도 이미
      start 이전에 끝났을 것이므로 범위 밖이다.
    """
    _, month_day = _REPRT_CODE_TO_QUARTER[reprt_code]
    period_end = date.fromisoformat(f"{bsns_year}{month_day}")
    if period_end > end:
        return False
    if period_end + timedelta(days=DISCLOSURE_GRACE_DAYS) < start:
        return False
    return True


def _recent_quarter_candidates(as_of: date, count: int) -> list[tuple[int, str]]:
    """`as_of` 시점에 period_end가 지난 최근 분기 `count`개를 최신순으로 반환한다.

    아직 끝나지 않은(period_end > as_of) 분기는 건너뛴다 — 예를 들어 as_of가 7월이면
    당해 3/4분기는 아직 끝나지 않았으므로 후보에서 제외되고 2분기(반기)부터 시작한다.
    """
    candidates: list[tuple[int, str]] = []
    year = as_of.year
    q_idx = len(_QUARTER_ORDER) - 1
    while len(candidates) < count:
        reprt_code = _QUARTER_ORDER[q_idx]
        _, month_day = _REPRT_CODE_TO_QUARTER[reprt_code]
        period_end = date.fromisoformat(f"{year}{month_day}")
        if period_end <= as_of:
            candidates.append((year, reprt_code))
        q_idx -= 1
        if q_idx < 0:
            q_idx = len(_QUARTER_ORDER) - 1
            year -= 1
    return candidates
