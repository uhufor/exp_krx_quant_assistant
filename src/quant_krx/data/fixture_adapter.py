from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .base import OHLCVData, ProviderMeta

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "sample_ohlcv.csv"
)


class FixtureAdapter:
    """테스트 픽스처 기반 어댑터 (네트워크 없음)."""

    def __init__(self, fixture_path: Path | None = None):
        self._path = fixture_path or FIXTURE_PATH
        self._df: pd.DataFrame | None = None

    @property
    def source_name(self) -> str:
        return "Fixture"

    def _load(self) -> pd.DataFrame:
        if self._df is None:
            self._df = pd.read_csv(self._path, dtype={"symbol": str}, parse_dates=["date"])
            self._df["symbol"] = self._df["symbol"].str.zfill(6)
            self._df["date"] = self._df["date"].dt.date
        return self._df

    def list_symbols(self, market: str = "KRX") -> list[str]:
        return self._load()["symbol"].unique().tolist()

    def fetch_ohlcv(self, symbol: str, start: date, end: date, interval: str = "1d") -> OHLCVData:
        df = self._load()
        mask = (df["symbol"] == symbol) & (df["date"] >= start) & (df["date"] <= end)
        cols = ["date", "open", "high", "low", "close", "volume", "symbol"]
        result = df[mask][cols].reset_index(drop=True)
        meta = ProviderMeta(source_name=self.source_name, fetched_at=datetime.utcnow())
        return OHLCVData(symbol=symbol, df=result, meta=meta)

    def fetch_benchmark(self, symbol_or_market: str, start: date, end: date) -> OHLCVData:
        # 픽스처에서 첫 번째 종목을 벤치마크로 사용
        symbols = self.list_symbols()
        return self.fetch_ohlcv(symbols[0], start, end)

    # 픽스처 5종목(005930/000660/006400/035420/051910)은 실제로 모두 KOSPI 상장 종목이다
    # (합성 가격 데이터일 뿐 종목코드 자체는 실존 코드를 그대로 씀) — 테스트 전용이라
    # KOSDAQ 예시가 필요 없는 한 이 고정 매핑으로 충분하다.
    _MARKET = "KOSPI"

    def fetch_metadata(self, symbols: list[str]) -> dict[str, dict]:
        return {
            s: {"symbol": s, "source": self.source_name, "market": self._MARKET} for s in symbols
        }

    def fetch_market_snapshot(self, date: date, market: str = "KRX") -> pd.DataFrame:
        df = self._load()
        result = df[df["date"] == date][["symbol", "close", "volume"]].reset_index(drop=True)
        result["trading_value"] = result["close"] * result["volume"]
        return result[["symbol", "close", "volume", "trading_value"]]
