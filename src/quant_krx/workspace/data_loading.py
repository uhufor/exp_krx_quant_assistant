from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from quant_krx.data.base import DataProvider
from quant_krx.data.fundamental_base import FundamentalProvider
from quant_krx.data.loader import load_factor_input
from quant_krx.data.upsert import upsert_fundamental
from quant_krx.factors import FactorInput
from quant_krx.storage.db import Database


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    result = df.set_index("date") if "date" in df.columns else df
    result.index = pd.to_datetime(result.index)
    result = result.sort_index()
    return result[["open", "high", "low", "close", "volume"]].astype(float)


def fetch_and_upsert_fundamentals(
    db: Database,
    symbols: list[str],
    provider: FundamentalProvider,
    *,
    start: date,
    end: date,
    as_of: date,
    kinds: frozenset[str],
) -> None:
    """required_data에 valuation/financials가 있을 때만 호출한다(AC-04 — ohlcv-only는 호출 0회).

    R01 FundamentalProvider·upsert_fundamental 단일 강제점·품질 게이트 경로를 그대로
    재사용하며(fetch-fundamental CLI와 동일 경로), 신규 수집 로직을 두지 않는다.
    """
    with db.cursor() as conn:
        if "valuation" in kinds:
            frame = provider.fetch_valuation(symbols, start, end)
            frame = frame.assign(source=provider.source_name, fetched_at=datetime.utcnow())
            upsert_fundamental(conn, "fundamental_daily", frame, as_of=as_of)
        if "financials" in kinds:
            frame = provider.fetch_financials(symbols, start, end)
            frame = frame.assign(source=provider.source_name, fetched_at=datetime.utcnow())
            upsert_fundamental(conn, "financial_statements", frame, as_of=as_of)


def build_factor_input_from_ohlcv(
    db: Database,
    symbol: str,
    ohlcv_raw: pd.DataFrame,
    *,
    start: date,
    end: date,
) -> FactorInput:
    """이미 조회된 OHLCV(raw, date 컬럼 포함 가능)로 FactorInput을 조립한다(중복 fetch 회피).

    data/는 factors/를 모르므로(INV-1) 두 계층을 모두 아는 상위 호출자(R03)가 조립을 수행한다.
    """
    ohlcv_df = _normalize_ohlcv(ohlcv_raw)
    with db.cursor() as conn:
        bundle = load_factor_input(conn, symbol, start=start, end=end, ohlcv=ohlcv_df)
    return FactorInput(ohlcv=bundle.ohlcv, valuation=bundle.valuation, financials=bundle.financials)


def build_factor_input(
    db: Database,
    symbol: str,
    *,
    ohlcv_provider: DataProvider,
    start: date,
    end: date,
) -> FactorInput:
    """OHLCV를 조회한 뒤 build_factor_input_from_ohlcv로 위임한다."""
    ohlcv_data = ohlcv_provider.fetch_ohlcv(symbol, start, end)
    return build_factor_input_from_ohlcv(db, symbol, ohlcv_data.df, start=start, end=end)
