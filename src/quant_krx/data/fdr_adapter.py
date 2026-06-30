from __future__ import annotations

from datetime import date, datetime

import FinanceDataReader as fdr
import pandas as pd

from .base import OHLCVData, ProviderMeta

KOSPI_BENCHMARK = "KS11"   # KOSPI 지수
KOSDAQ_BENCHMARK = "KQ11"  # KOSDAQ 지수


class FDRAdapter:
    """FinanceDataReader 기반 KRX 데이터 제공자."""

    @property
    def source_name(self) -> str:
        return "FinanceDataReader"

    def list_symbols(self, market: str = "KRX") -> list[str]:
        """KRX/KOSPI/KOSDAQ 상장 종목 코드 목록."""
        try:
            df = fdr.StockListing(market)
            # 컬럼명이 버전마다 다를 수 있음
            code_col = next((c for c in df.columns if c in ("Code", "Symbol", "종목코드")), None)
            if code_col is None:
                return []
            return df[code_col].astype(str).str.zfill(6).tolist()
        except Exception:
            return []

    def fetch_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> OHLCVData:
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        df = fdr.DataReader(symbol, start=start.isoformat(), end=end.isoformat())
        df = self._normalize(df)
        return OHLCVData(symbol=symbol, df=df, meta=meta)

    def fetch_benchmark(self, symbol_or_market: str, start: date, end: date) -> OHLCVData:
        in_kospi = symbol_or_market in ("KRX", "KOSPI", KOSPI_BENCHMARK)
        ticker = KOSPI_BENCHMARK if in_kospi else symbol_or_market
        return self.fetch_ohlcv(ticker, start, end)

    def fetch_metadata(self, symbols: list[str]) -> dict[str, dict]:
        try:
            df = fdr.StockListing("KRX")
            code_col = next((c for c in df.columns if c in ("Code", "Symbol", "종목코드")), None)
            name_col = next((c for c in df.columns if c in ("Name", "종목명")), None)
            if code_col is None:
                return {}
            result = {}
            for sym in symbols:
                row = df[df[code_col].astype(str).str.zfill(6) == sym]
                if row.empty:
                    result[sym] = {"symbol": sym}
                else:
                    r = row.iloc[0].to_dict()
                    result[sym] = {
                        "symbol": sym,
                        "name": str(r.get(name_col, "")) if name_col else "",
                        "source": self.source_name,
                    }
            return result
        except Exception:
            return {s: {"symbol": s} for s in symbols}

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.reset_index()
        # 날짜 컬럼 통일
        _date_names = ("date", "index", "datetime")
        date_col = next((c for c in df.columns if c.lower() in _date_names), df.columns[0])
        df = df.rename(columns={date_col: "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        # OHLCV 컬럼 소문자 통일
        col_map = {}
        for c in df.columns:
            lc = c.lower()
            if lc in ("open", "high", "low", "close", "volume", "change"):
                col_map[c] = lc
        df = df.rename(columns=col_map)
        # 필요 컬럼만
        keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
        df = df[keep].dropna(subset=["close"])
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        return df.reset_index(drop=True)
