from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass
class ProviderMeta:
    source_name: str
    fetched_at: datetime
    adjustment: str = "none"   # "none" | "forward" | "backward"
    notes: str = ""


@dataclass
class OHLCVData:
    symbol: str
    df: pd.DataFrame           # columns: date, open, high, low, close, volume (모두 float/int)
    meta: ProviderMeta

    def validate(self) -> list[str]:
        """기본 데이터 품질 검증. 문제 목록 반환 (빈 리스트 = OK)."""
        issues = []
        required = {"date", "open", "high", "low", "close", "volume"}
        missing = required - set(self.df.columns)
        if missing:
            issues.append(f"Missing columns: {missing}")
            return issues
        if self.df["close"].le(0).any():
            issues.append("Non-positive close price detected")
        if self.df["date"].duplicated().any():
            issues.append("Duplicate dates detected")
        if self.df.empty:
            issues.append("Empty OHLCV data")
        return issues


@runtime_checkable
class DataProvider(Protocol):
    @property
    def source_name(self) -> str: ...

    def list_symbols(self, market: str = "KRX", as_of: date | None = None) -> list[str]:
        """상장 종목 코드 목록. as_of를 주면 **그 시점 기준** 목록을 반환한다.

        as_of가 중요한 이유: 과거 구간을 백테스트하면서 "현재 상장 종목"만 후보로 삼으면
        그 사이 상장폐지된 종목이 통째로 빠져 성과가 부풀려진다(생존 편향). 시점별 목록을
        지원하지 않는 provider는 as_of를 무시할 수 있으나, 그 경우 편향이 남는다.
        """
        ...

    def list_etf_symbols(self, as_of: date | None = None) -> set[str]:
        """ETF 종목 코드 집합(스크리닝 제외 필터용).

        provider를 통하는 이유: 예전에는 스크리닝이 pykrx를 직접 호출해서, fixture
        데이터소스로 오프라인 실행을 해도 ETF 필터가 켜져 있으면 KRX 로그인을 시도하고
        자격증명이 없으면 스크리닝 자체가 실패했다.
        """
        return set()

    def list_etn_symbols(self, as_of: date | None = None) -> set[str]:
        """ETN 종목 코드 집합(스크리닝 제외 필터용). list_etf_symbols와 같은 이유로 분리."""
        return set()

    def fetch_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> OHLCVData: ...

    def fetch_benchmark(
        self,
        symbol_or_market: str,
        start: date,
        end: date,
    ) -> OHLCVData: ...

    def fetch_metadata(self, symbols: list[str]) -> dict[str, dict]:
        """종목별 메타데이터. 반환 dict의 값은 최소 {"symbol": str}이며, 구현체가 알 수 있으면
        "name"(종목명)과 "market"("KOSPI" | "KOSDAQ" | 미상 시 "")도 채운다. 두 키 모두
        선택 사항(호출자는 .get()으로 안전하게 접근해야 한다)."""
        ...

    def fetch_market_snapshot(self, date: date, market: str = "KRX") -> pd.DataFrame:
        """특정 일자 시장 전체 종목의 스냅샷(종가/거래량/거래대금)을 한 번에 조회한다.

        스크리닝(거래대금/거래량 순위 등)이 종목별 순차 조회 없이 시장 전체를
        일괄 조회할 수 있도록 하기 위한 메서드. 반환 컬럼 계약:
        - symbol (str, 6자리 zfill)
        - close (float)
        - volume (int)
        - trading_value (float, 네이티브 거래대금 — 체결가×수량 합. close*volume 근사치가 아님)
        """
        ...
