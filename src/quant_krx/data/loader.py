from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

_VALUATION_VALUE_COLUMNS = (
    "close", "per", "pbr", "eps", "bps", "div", "dps", "market_cap", "shares",
)


@dataclass(frozen=True)
class FundamentalBundle:
    """DB에서 재구성한 단일 종목 펀더멘털 번들.

    quant_krx.factors.base.FactorInput과 형상이 동일(ohlcv/valuation/financials)하지만,
    data/는 factors/를 역참조하지 않는다(INV-1 단방향, DESIGN-R01 §2.2 "데이터 계약,
    코드 의존 아님"). 실제 FactorInput 조립은 두 계층을 모두 아는 상위 호출자(R03)가 수행한다.
    """

    ohlcv: pd.DataFrame
    valuation: pd.DataFrame | None
    financials: pd.DataFrame | None


def load_factor_input(
    conn,
    symbol: str,
    *,
    start: date | None = None,
    end: date | None = None,
    ohlcv: pd.DataFrame,
) -> FundamentalBundle:
    """fundamental_daily/financial_statements에서 단일 symbol을 조회해 재구성한다.

    valuation: date 오름차순 DatetimeIndex, 값 컬럼 재구성.
    financials: disclosure_date 오름차순 RangeIndex(원본, as-of 미정렬).
    데이터 부재 시 해당 필드는 None(TR-R01-007 degrade 경로로 이어짐).
    """
    valuation = _load_valuation(conn, symbol, start, end)
    financials = _load_financials(conn, symbol, start, end)
    return FundamentalBundle(ohlcv=ohlcv, valuation=valuation, financials=financials)


def _load_valuation(
    conn, symbol: str, start: date | None, end: date | None
) -> pd.DataFrame | None:
    cols = ", ".join(_VALUATION_VALUE_COLUMNS)
    query = f"SELECT date, {cols} FROM fundamental_daily WHERE symbol = ?"
    params: list[object] = [symbol]
    if start is not None:
        query += " AND date >= ?"
        params.append(start)
    if end is not None:
        query += " AND date <= ?"
        params.append(end)
    query += " ORDER BY date ASC"
    df = conn.execute(query, params).df()
    if df.empty:
        return None
    # DuckDB .df()는 datetime64[us]를 반환하므로 pandas 표준 ns 정밀도로 정규화
    # (FR-05a: valuation.index == ohlcv.index 동일 trading 캘린더 계약 유지).
    df["date"] = pd.to_datetime(df["date"]).astype("datetime64[ns]")
    return df.set_index("date")


def _load_financials(
    conn, symbol: str, start: date | None, end: date | None
) -> pd.DataFrame | None:
    query = "SELECT * FROM financial_statements WHERE symbol = ?"
    params: list[object] = [symbol]
    if start is not None:
        query += " AND disclosure_date >= ?"
        params.append(start)
    if end is not None:
        query += " AND disclosure_date <= ?"
        params.append(end)
    query += " ORDER BY disclosure_date ASC"
    df = conn.execute(query, params).df()
    if df.empty:
        return None
    return df.reset_index(drop=True)
