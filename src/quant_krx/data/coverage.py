from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from quant_krx.data.dart_fundamental import DISCLOSURE_GRACE_DAYS

_QUARTER_END_MONTH_DAY = {1: "-03-31", 2: "-06-30", 3: "-09-30", 4: "-12-31"}


def quarter_end(year: int, quarter: int) -> date:
    return date.fromisoformat(f"{year}{_QUARTER_END_MONTH_DAY[quarter]}")


def next_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year + 1, 1) if quarter == 4 else (year, quarter + 1)


def is_financials_stale(latest: tuple[int, int] | None, as_of: date) -> bool:
    """`latest` 다음 분기가 이미 공시됐어야 하는데 없으면(또는 데이터 자체가 없으면) 갱신 대상.

    공시 유예(`DISCLOSURE_GRACE_DAYS`)를 지나도 다음 분기가 안 들어와 있으면 "뒤처졌다"고
    본다. 증분 수집(`screening/fundamental_sync.py`)과 신선도 점검(`data/freshness.py`)이
    같은 기준을 써야 "수집은 건너뛰는데 점검은 경고하는" 모순이 생기지 않으므로 여기 둔다.
    """
    if latest is None:
        return True
    ny, nq = next_quarter(*latest)
    return quarter_end(ny, nq) + timedelta(days=DISCLOSURE_GRACE_DAYS) <= as_of


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
