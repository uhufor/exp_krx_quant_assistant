from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def existing_valuation_coverage(conn, symbols: list[str]) -> dict[str, tuple[date, date]]:
    """symbol별 fundamental_daily 기존 커버리지(min/max date)를 조회한다."""
    if not symbols:
        return {}
    df = conn.execute(
        "SELECT symbol, MIN(date) AS min_date, MAX(date) AS max_date "
        "FROM fundamental_daily WHERE symbol = ANY(?) GROUP BY symbol",
        [symbols],
    ).df()
    return {
        row["symbol"]: (pd.Timestamp(row["min_date"]).date(), pd.Timestamp(row["max_date"]).date())
        for _, row in df.iterrows()
    }


def date_range_gaps(
    existing: tuple[date, date] | None, start: date, end: date
) -> list[tuple[date, date]]:
    """요청 구간[start, end] 중 기존 커버리지 밖(이전/이후)만 반환한다.

    기존 구간 내부(거래 캘린더상 자연스러운 결측 제외)는 재수집하지 않는다 — 이미 있는
    데이터는 건드리지 않고, 경계 바깥의 부족분만 최소로 채운다.
    """
    if existing is None:
        return [(start, end)]
    existing_min, existing_max = existing
    gaps: list[tuple[date, date]] = []
    if start < existing_min:
        gaps.append((start, min(existing_min - timedelta(days=1), end)))
    if end > existing_max:
        gaps.append((max(existing_max + timedelta(days=1), start), end))
    return gaps


def latest_financials_period(conn, symbols: list[str]) -> dict[str, tuple[int, int]]:
    """symbol별 financial_statements 최신 (fiscal_year, fiscal_quarter)만 반환(신선도 판정용)."""
    if not symbols:
        return {}
    df = conn.execute(
        "SELECT symbol, fiscal_year, fiscal_quarter FROM financial_statements "
        "WHERE symbol = ANY(?) "
        "QUALIFY ROW_NUMBER() OVER "
        "(PARTITION BY symbol ORDER BY fiscal_year DESC, fiscal_quarter DESC) = 1",
        [symbols],
    ).df()
    return {
        row["symbol"]: (int(row["fiscal_year"]), int(row["fiscal_quarter"]))
        for _, row in df.iterrows()
    }


def existing_financials_periods(conn, symbols: list[str]) -> dict[str, set[tuple[int, int]]]:
    """symbol별 financial_statements 기존 (fiscal_year, fiscal_quarter) 커버리지를 조회한다.

    scope(연결/별도) 무관 — 해당 분기가 어느 쪽으로든 이미 있으면 커버된 것으로 본다.
    """
    if not symbols:
        return {}
    df = conn.execute(
        "SELECT DISTINCT symbol, fiscal_year, fiscal_quarter FROM financial_statements "
        "WHERE symbol = ANY(?)",
        [symbols],
    ).df()
    result: dict[str, set[tuple[int, int]]] = {}
    for _, row in df.iterrows():
        result.setdefault(row["symbol"], set()).add(
            (int(row["fiscal_year"]), int(row["fiscal_quarter"]))
        )
    return result
