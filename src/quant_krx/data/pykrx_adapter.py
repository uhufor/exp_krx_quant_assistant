from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from .base import OHLCVData, ProviderMeta


def _krx_stock():
    """Lazy import of pykrx.stock to avoid pkg_resources import at module load."""
    from pykrx import stock as _stock  # noqa: PLC0415
    return _stock


class PyKrxAdapter:
    """PyKrx 기반 KRX 데이터 제공자."""

    @property
    def source_name(self) -> str:
        return "PyKrx"

    def list_symbols(self, market: str = "KOSPI") -> list[str]:
        try:
            s = _krx_stock()
            today_str = date.today().strftime("%Y%m%d")
            if market in ("KOSPI", "KRX"):
                tickers = s.get_market_ticker_list(today_str, market="KOSPI")
                tickers += s.get_market_ticker_list(today_str, market="KOSDAQ")
            else:
                tickers = s.get_market_ticker_list(today_str, market=market)
            return [t.zfill(6) for t in tickers]
        except Exception:
            return []

    def fetch_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> OHLCVData:
        s = _krx_stock()
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        df = s.get_market_ohlcv_by_date(start_str, end_str, symbol)
        df = self._normalize(df, symbol)
        return OHLCVData(symbol=symbol, df=df, meta=meta)

    def fetch_benchmark(self, symbol_or_market: str, start: date, end: date) -> OHLCVData:
        # KOSPI 지수 티커: 1028
        ticker = "1028" if symbol_or_market in ("KRX", "KOSPI") else symbol_or_market
        s = _krx_stock()
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        df = s.get_index_ohlcv_by_date(start_str, end_str, ticker)
        df = self._normalize(df, ticker)
        return OHLCVData(symbol=ticker, df=df, meta=meta)

    def fetch_metadata(self, symbols: list[str]) -> dict[str, dict]:
        result = {}
        for sym in symbols:
            try:
                s = _krx_stock()
                name = s.get_market_ticker_name(sym)
                result[sym] = {"symbol": sym, "name": name, "source": self.source_name}
            except Exception:
                result[sym] = {"symbol": sym}
        return result

    def _normalize(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.reset_index()
        date_col = df.columns[0]
        df = df.rename(columns={date_col: "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        # PyKrx 컬럼명 한글 → 영문 매핑
        col_map = {
            "시가": "open", "고가": "high", "저가": "low",
            "종가": "close", "거래량": "volume",
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }
        df = df.rename(columns=col_map)
        keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
        df = df[keep].dropna(subset=["close"])
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        return df.reset_index(drop=True)
