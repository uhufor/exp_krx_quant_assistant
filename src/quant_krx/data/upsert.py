from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .quality import ExcludedRow, apply_quality_gate

_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "fundamental_daily": (
        "symbol", "date", "close", "per", "pbr", "eps", "bps", "div", "dps",
        "market_cap", "shares", "source", "fetched_at",
    ),
    "financial_statements": (
        "symbol", "fiscal_year", "fiscal_quarter", "statement_scope", "revenue",
        "gross_profit", "operating_income", "net_income", "pretax_income", "income_tax",
        "total_assets", "total_debt", "total_equity", "current_assets", "current_liabilities",
        "operating_cash_flow", "interest_expense", "depreciation_amortization",
        "cash_and_equivalents", "invested_capital", "period_end", "disclosure_date",
        "source", "fetched_at",
    ),
}


@dataclass(frozen=True)
class UpsertResult:
    table: str
    accepted: int
    excluded: tuple[ExcludedRow, ...]


def upsert_fundamental(
    conn, table: str, frame: pd.DataFrame, *, as_of: date
) -> UpsertResult:
    """품질 게이트 통과 행만 INSERT OR REPLACE하는 단일 강제점 (TR-R01-009, A1-i, DESIGN §7.2).

    frame은 대상 테이블의 전체 컬럼(source/fetched_at 포함)을 이미 갖추고 있어야 한다.
    fetch-fundamental CLI와 Daily 자동수집이 이 함수를 공유해 우회 없이 재사용한다(FR-17a).
    재실행 시 INSERT OR REPLACE로 멱등(중복 0).
    """
    if frame.empty:
        return UpsertResult(table=table, accepted=0, excluded=())

    accepted, excluded = apply_quality_gate(table, frame, as_of=as_of)
    if accepted.empty:
        return UpsertResult(table=table, accepted=0, excluded=excluded)

    columns = _TABLE_COLUMNS[table]
    ordered = accepted[list(columns)]
    conn.register("_upsert_tmp", ordered)
    col_list = ", ".join(columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({col_list}) SELECT {col_list} FROM _upsert_tmp"
    )
    conn.unregister("_upsert_tmp")

    return UpsertResult(table=table, accepted=len(ordered), excluded=excluded)
