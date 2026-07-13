from __future__ import annotations

import pandas as pd

_SCOPE_PRIORITY = {"consolidated": 0, "separate": 1}


def unify_financials_scope(financials: pd.DataFrame) -> pd.DataFrame:
    """(fiscal_year, fiscal_quarter)별로 연결(consolidated) 우선, 부재 시 별도(separate) 폴백."""
    df = financials.copy()
    df["_priority"] = df["statement_scope"].map(_SCOPE_PRIORITY)
    df = df.sort_values(["fiscal_year", "fiscal_quarter", "_priority"])
    df = df.drop_duplicates(subset=["fiscal_year", "fiscal_quarter"], keep="first")
    return df.drop(columns=["_priority"])


def merge_asof_daily(unified: pd.DataFrame, daily_index: pd.DatetimeIndex) -> pd.DataFrame:
    """이미 단일 계열로 정리된(unify_financials_scope 결과) 프레임을 daily_index에
    disclosure_date 기준 as-of(backward) 정렬한다.

    (disclosure_date asc, period_end desc) 정렬 후 동일 disclosure_date는
    최상단(period_end 최신)만 유지하고 merge_asof(backward)로 병합한다.
    최초 공시 이전 구간은 좌측 미매치로 자연 NaN.
    """
    tie_broken = unified.sort_values(["disclosure_date", "period_end"], ascending=[True, False])
    tie_broken = tie_broken.drop_duplicates(subset=["disclosure_date"], keep="first")
    tie_broken = tie_broken.sort_values("disclosure_date")

    # merge_asof는 좌/우 키의 datetime64 단위(ns/us)가 정확히 일치해야 하므로 ns로 통일한다
    # (DB round-trip 등 호출자에 따라 datetime64[us]가 유입될 수 있음).
    left = pd.DataFrame(
        {"date": pd.DatetimeIndex(daily_index).astype("datetime64[ns]")}
    ).sort_values("date")
    right = tie_broken.assign(
        disclosure_date=pd.to_datetime(tie_broken["disclosure_date"]).astype("datetime64[ns]")
    )

    aligned = pd.merge_asof(
        left, right, left_on="date", right_on="disclosure_date", direction="backward"
    )
    aligned = aligned.set_index("date").reindex(pd.DatetimeIndex(daily_index))
    return aligned


def align_financials(financials: pd.DataFrame, daily_index: pd.DatetimeIndex) -> pd.DataFrame:
    """재무제표 분기 프레임을 daily_index에 as-of(backward) 정렬한다 (DESIGN-R01 §6.3).

    1) 연결/별도 폴백으로 단일 계열 구성(unify_financials_scope)
    2) tie-break + merge_asof(backward)로 daily_index에 병합(merge_asof_daily)
    """
    unified = unify_financials_scope(financials)
    return merge_asof_daily(unified, daily_index)
