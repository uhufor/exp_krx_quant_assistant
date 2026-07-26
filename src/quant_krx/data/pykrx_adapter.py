from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from .base import OHLCVData, ProviderMeta


def _krx_stock():
    """Lazy import of pykrx.stock to avoid pkg_resources import at module load."""
    from pykrx import stock as _stock  # noqa: PLC0415
    return _stock


def _resolve_trading_day(s, date_str: str) -> str:
    """요청 일자가 휴장일(주말/공휴일)이면 직전 영업일로 보정한다.

    list_symbols/fetch_market_snapshot가 date.today()를 그대로 조회하면, 오늘이
    휴장일일 때 pykrx가 빈 결과를 반환해 스크리닝 전체가 EmptyUniverseError로
    실패한다. 보정 조회 자체가 실패하면(예: 달력 조회 불가 환경) 원본 날짜를
    그대로 반환한다 — 이 경우 최종 조회는 여전히 실패할 수 있으나 보정 로직이
    새로운 예외를 추가로 만들지는 않는다.
    """
    try:
        return s.get_nearest_business_day_in_a_week(date_str, prev=True)
    except Exception:
        return date_str


class PyKrxAdapter:
    """PyKrx 기반 KRX 데이터 제공자."""

    def __init__(self) -> None:
        # list_symbols()가 이미 조회한 KOSPI/KOSDAQ 소속 정보를 재사용하기 위한
        # 인스턴스 캐시(fetch_metadata 참고) — 매 요청마다 새 인스턴스가 만들어지므로
        # (api/deps.py::get_data_provider) 요청 하나 안에서만 유효하면 충분하다.
        self._market_cache: dict[str, str] = {}

    @property
    def source_name(self) -> str:
        return "PyKrx"

    def list_symbols(self, market: str = "KOSPI") -> list[str]:
        try:
            s = _krx_stock()
            today_str = _resolve_trading_day(s, date.today().strftime("%Y%m%d"))
            if market in ("KOSPI", "KRX"):
                kospi = s.get_market_ticker_list(today_str, market="KOSPI")
                kosdaq = s.get_market_ticker_list(today_str, market="KOSDAQ")
                for t in kospi:
                    self._market_cache[t.zfill(6)] = "KOSPI"
                for t in kosdaq:
                    self._market_cache[t.zfill(6)] = "KOSDAQ"
                tickers = kospi + kosdaq
            else:
                tickers = s.get_market_ticker_list(today_str, market=market)
                for t in tickers:
                    self._market_cache[t.zfill(6)] = market
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

    def fetch_market_snapshot(self, date: date, market: str = "KRX") -> pd.DataFrame:
        # NOTE: list_symbols와 달리 예외를 삼키지 않고 그대로 전파한다. 스크리닝
        # 계층이 빈 유니버스를 감지해 EmptyUniverseError로 승격시킬 책임을 지므로,
        # 여기서 삼켜 빈 DataFrame을 반환하면 "정상적으로 0종목"과 "조회 실패"를
        # 구분할 수 없게 된다.
        s = _krx_stock()
        date_str = _resolve_trading_day(s, date.strftime("%Y%m%d"))
        if market in ("KOSPI", "KRX"):
            kospi = s.get_market_ohlcv_by_ticker(date_str, market="KOSPI")
            kosdaq = s.get_market_ohlcv_by_ticker(date_str, market="KOSDAQ")
            df = pd.concat([kospi, kosdaq])
        else:
            df = s.get_market_ohlcv_by_ticker(date_str, market=market)
        return self._normalize_snapshot(df)

    def list_trading_days(self, start: date, end: date) -> list[date]:
        """구간 내 실제 KRX 영업일만 반환한다(주말·공휴일 제외).

        DataProvider 프로토콜에는 없는 PyKrx 전용 부가 능력 — 벌크 조회(날짜별)에서
        불필요한 휴장일 호출을 피하기 위해 universe_data.py가 hasattr()로 존재 여부를
        확인해 선택적으로 사용한다.
        """
        s = _krx_stock()
        days = s.get_previous_business_days(
            fromdate=start.strftime("%Y%m%d"), todate=end.strftime("%Y%m%d")
        )
        return [pd.Timestamp(d).date() for d in days]

    def fetch_ohlcv_bulk_by_date(self, date: date, market: str = "KRX") -> pd.DataFrame:
        """단일 거래일 기준 전 종목 OHLCV를 1콜로 벌크 조회한다(종목별 순차 fetch_ohlcv
        대체 최적화 경로). fetch_market_snapshot과 동일한 get_market_ohlcv_by_ticker를
        재사용하되 open/high/low까지 포함해 반환한다.

        DataProvider 프로토콜에는 없는 PyKrx 전용 부가 능력이며, universe_data.py가
        hasattr()로 존재 여부를 확인해 선택적으로 사용한다(FDR/Fixture는 종목 단위
        API라 이 최적화가 구조상 불가능 — 미구현 상태로 둔다).
        """
        s = _krx_stock()
        date_str = _resolve_trading_day(s, date.strftime("%Y%m%d"))
        if market in ("KOSPI", "KRX"):
            kospi = s.get_market_ohlcv_by_ticker(date_str, market="KOSPI")
            kosdaq = s.get_market_ohlcv_by_ticker(date_str, market="KOSDAQ")
            df = pd.concat([kospi, kosdaq])
        else:
            df = s.get_market_ohlcv_by_ticker(date_str, market=market)
        return self._normalize_bulk_ohlcv(df, date)

    def fetch_metadata(self, symbols: list[str]) -> dict[str, dict]:
        s = _krx_stock()
        market_by_symbol = self._market_membership(s, symbols)
        result = {}
        for sym in symbols:
            try:
                name = s.get_market_ticker_name(sym)
                result[sym] = {
                    "symbol": sym,
                    "name": name,
                    "source": self.source_name,
                    "market": market_by_symbol.get(sym, ""),
                }
            except Exception:
                result[sym] = {"symbol": sym, "market": market_by_symbol.get(sym, "")}
        return result

    def _market_membership(self, s, symbols: list[str]) -> dict[str, str]:
        """symbol→KOSPI/KOSDAQ 매핑을 반환한다.

        list_symbols()가 이미 같은 인스턴스에서 호출됐다면(스크리닝 run()의 통상 경로 —
        universe 해석 시 list_symbols 호출 후 마지막에 fetch_metadata 호출) 그 결과를
        그대로 재사용해 네트워크 호출을 추가하지 않는다. 요청 대상 symbols 중 캐시에
        없는 종목이 하나라도 있으면(예: fetch_metadata를 list_symbols 없이 단독 호출한
        경우) 그때만 KOSPI/KOSDAQ 목록을 새로 조회한다 — 매번 추가 호출을 만들면 그만큼
        간헐적 KRX 세션 실패에 노출되는 지점이 늘어난다."""
        if all(sym in self._market_cache for sym in symbols):
            return self._market_cache
        today_str = _resolve_trading_day(s, date.today().strftime("%Y%m%d"))
        for market in ("KOSPI", "KOSDAQ"):
            try:
                tickers = s.get_market_ticker_list(today_str, market=market)
            except Exception:
                continue
            for t in tickers:
                self._market_cache[t.zfill(6)] = market
        return self._market_cache

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

    def _normalize_bulk_ohlcv(self, df: pd.DataFrame, as_of: date) -> pd.DataFrame:
        df = df.copy()
        df = df.reset_index()
        ticker_col = df.columns[0]
        df = df.rename(columns={ticker_col: "symbol"})
        col_map = {
            "시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume",
        }
        df = df.rename(columns=col_map)
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        df["date"] = as_of
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        return df[["symbol", "date", "open", "high", "low", "close", "volume"]].reset_index(
            drop=True
        )

    def _normalize_snapshot(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = df.reset_index()
        ticker_col = df.columns[0]
        df = df.rename(columns={ticker_col: "symbol"})
        # get_market_ohlcv_by_ticker 반환 컬럼: 시가,고가,저가,종가,거래량,거래대금,등락률
        # 거래대금은 체결가×수량 합산 네이티브 값(close*volume 근사치가 아님).
        col_map = {"종가": "close", "거래량": "volume", "거래대금": "trading_value"}
        df = df.rename(columns=col_map)
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        df["trading_value"] = pd.to_numeric(df["trading_value"], errors="coerce")
        return df[["symbol", "close", "volume", "trading_value"]].reset_index(drop=True)
