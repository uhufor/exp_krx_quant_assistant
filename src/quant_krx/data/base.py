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

    def list_symbols(self, market: str = "KRX") -> list[str]: ...

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

    def fetch_metadata(self, symbols: list[str]) -> dict[str, dict]: ...

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
