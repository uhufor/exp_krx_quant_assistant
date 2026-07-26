from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

_DEFAULT_CACHE_PATH = Path.home() / ".cache" / "quant_krx" / "dart_missing_periods.parquet"
DEFAULT_TTL = timedelta(hours=1)
_COLUMNS = ("symbol", "fiscal_year", "fiscal_quarter", "checked_at")


class DartMissingPeriodCache:
    """DART에 "아직 공시 없음"(013)으로 확인된 (symbol, 분기)를 TTL(기본 1시간) 동안
    재조회 없이 건너뛴다.

    성공한 조회는 `financial_statements`에 저장되어 다음 실행에서 `skip_periods`가 자연히
    걸러주지만, "아직 없더라"는 부정 결과는 저장할 곳이 없어 매 실행마다 재확인되는 문제가
    있었다(TRD-R04 후속 수정). TTL 안에서는 재확인을 생략하고, TTL이 지나면 다시 확인한다
    (사용자 확정: 1시간 단위).

    호출마다 디스크 I/O를 하지 않도록 메모리에 로드해 실행 중 갱신하고, `flush()`가 호출될
    때(어댑터 `close()` 시점)만 한 번 저장한다.
    """

    def __init__(self, cache_path: Path | None = None, ttl: timedelta = DEFAULT_TTL) -> None:
        self._path = cache_path or _DEFAULT_CACHE_PATH
        self._ttl = ttl
        self._df: pd.DataFrame | None = None
        self._dirty = False

    def _load(self) -> pd.DataFrame:
        if self._df is None:
            if self._path.exists():
                self._df = pd.read_parquet(self._path)
            else:
                self._df = pd.DataFrame(columns=list(_COLUMNS))
        return self._df

    def _match_mask(self, df: pd.DataFrame, symbol: str, fiscal_year: int, fiscal_quarter: int):
        return (
            (df["symbol"] == symbol)
            & (df["fiscal_year"] == fiscal_year)
            & (df["fiscal_quarter"] == fiscal_quarter)
        )

    def is_recently_checked(
        self, symbol: str, fiscal_year: int, fiscal_quarter: int, *, now: datetime
    ) -> bool:
        df = self._load()
        match = df[self._match_mask(df, symbol, fiscal_year, fiscal_quarter)]
        if match.empty:
            return False
        last_checked = pd.Timestamp(match["checked_at"].max()).to_pydatetime()
        return (now - last_checked) < self._ttl

    def record_missing(
        self, symbol: str, fiscal_year: int, fiscal_quarter: int, *, now: datetime
    ) -> None:
        df = self._load()
        remaining = df[~self._match_mask(df, symbol, fiscal_year, fiscal_quarter)]
        new_row = pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "fiscal_year": fiscal_year,
                    "fiscal_quarter": fiscal_quarter,
                    "checked_at": now,
                }
            ]
        )
        if remaining.empty:
            self._df = new_row
        else:
            self._df = pd.concat([remaining, new_row], ignore_index=True)
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._load().to_parquet(self._path, index=False)
        self._dirty = False
