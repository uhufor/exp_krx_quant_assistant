from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd

VALUATION_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "sample_valuation.csv"
)
FINANCIALS_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "sample_financials.csv"
)

_VALUATION_COLUMNS = (
    "symbol", "date", "close", "per", "pbr", "eps", "bps", "div", "dps", "market_cap", "shares",
)


class FixtureFundamentalAdapter:
    """테스트 픽스처 기반 펀더멘털 어댑터 (네트워크 없음). OHLCV 픽스처와 동일 종목 정합."""

    def __init__(
        self,
        valuation_path: Path | None = None,
        financials_path: Path | None = None,
    ):
        self._valuation_path = valuation_path or VALUATION_FIXTURE_PATH
        self._financials_path = financials_path or FINANCIALS_FIXTURE_PATH
        self._valuation_df: pd.DataFrame | None = None
        self._financials_df: pd.DataFrame | None = None

    @property
    def source_name(self) -> str:
        return "Fixture"

    def _load_valuation(self) -> pd.DataFrame:
        if self._valuation_df is None:
            df = pd.read_csv(
                self._valuation_path, dtype={"symbol": str}, parse_dates=["date"]
            )
            df["symbol"] = df["symbol"].str.zfill(6)
            df["date"] = df["date"].dt.date
            df["per"] = pd.NA
            df["pbr"] = pd.NA
            self._valuation_df = df[list(_VALUATION_COLUMNS)]
        return self._valuation_df

    def _load_financials(self) -> pd.DataFrame:
        if self._financials_df is None:
            df = pd.read_csv(
                self._financials_path,
                dtype={"symbol": str},
                parse_dates=["period_end", "disclosure_date"],
            )
            df["symbol"] = df["symbol"].str.zfill(6)
            df["period_end"] = df["period_end"].dt.date
            df["disclosure_date"] = df["disclosure_date"].dt.date
            self._financials_df = df
        return self._financials_df

    def fetch_valuation(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        df = self._load_valuation()
        mask = df["symbol"].isin(symbols) & (df["date"] >= start) & (df["date"] <= end)
        return df[mask].reset_index(drop=True)

    def fetch_financials(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        df = self._load_financials()
        mask = (
            df["symbol"].isin(symbols)
            & (df["disclosure_date"] >= start)
            & (df["disclosure_date"] <= end)
        )
        return df[mask].reset_index(drop=True)
