from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

import pandas as pd


class QualityViolation(str, Enum):
    DUPLICATE_PK = "duplicate_pk"
    NON_ASCENDING_DATE = "non_ascending_date"
    FUTURE_DATE = "future_date"
    NEGATIVE_FIELD = "negative_field"


@dataclass(frozen=True)
class ExcludedRow:
    symbol: str
    key: str
    reason: QualityViolation
    detail: str


_TABLE_QUALITY_CONFIG: dict[str, dict] = {
    "fundamental_daily": {
        "pk_columns": ("symbol", "date"),
        "date_column": "date",
        "negative_check_columns": ("market_cap", "shares"),
    },
    "financial_statements": {
        "pk_columns": ("symbol", "fiscal_year", "fiscal_quarter", "statement_scope"),
        "date_column": "disclosure_date",
        "negative_check_columns": (),
    },
}

_DETAIL_MESSAGES = {
    QualityViolation.DUPLICATE_PK: "동일 PK가 배치 내에 중복 존재합니다(첫 행만 채택).",
    QualityViolation.NON_ASCENDING_DATE: "동일 심볼 내 직전 행보다 날짜가 앞섭니다(오름차순 위반).",
    QualityViolation.FUTURE_DATE: "기준 시각(as_of) 이후의 미래 날짜입니다.",
    QualityViolation.NEGATIVE_FIELD: "음수가 허용되지 않는 필드에 음수 값이 존재합니다.",
}


def _format_key(row: pd.Series, pk_columns: list[str]) -> str:
    return ", ".join(f"{col}={row[col]}" for col in pk_columns)


def apply_quality_gate(
    table: str, frame: pd.DataFrame, *, as_of: date
) -> tuple[pd.DataFrame, tuple[ExcludedRow, ...]]:
    """upsert 직전 단일 강제점에서 4종 품질 검사를 수행한다 (TR-R01-009, A1-i).

    위반 행은 제외하고 사유와 함께 반환한다(수집 전체 중단 없음).
    """
    if frame.empty:
        return frame, ()

    config = _TABLE_QUALITY_CONFIG[table]
    pk_columns = list(config["pk_columns"])
    date_column = config["date_column"]
    negative_columns = config["negative_check_columns"]

    df = frame.reset_index(drop=True).copy()
    df[date_column] = pd.to_datetime(df[date_column])
    # QualityViolation은 str 서브클래스라 Series에 직접 담으면 pandas가 고정폭 유니코드로
    # 강제 변환해 값이 잘릴 수 있다 — .value(순수 str)만 저장하고 반환 직전에 복원한다.
    reason = pd.Series(pd.NA, index=df.index, dtype="object")

    dup_mask = df.duplicated(subset=pk_columns, keep="first")
    reason = reason.mask(dup_mask & reason.isna(), QualityViolation.DUPLICATE_PK.value)

    prev_date = df.groupby("symbol")[date_column].shift(1)
    non_ascending_mask = df[date_column] < prev_date
    reason = reason.mask(
        non_ascending_mask & reason.isna(), QualityViolation.NON_ASCENDING_DATE.value
    )

    future_mask = df[date_column] > pd.Timestamp(as_of)
    reason = reason.mask(future_mask & reason.isna(), QualityViolation.FUTURE_DATE.value)

    for col in negative_columns:
        negative_mask = df[col].notna() & (df[col] < 0)
        reason = reason.mask(
            negative_mask & reason.isna(), QualityViolation.NEGATIVE_FIELD.value
        )

    excluded_mask = reason.notna()
    excluded_rows = tuple(
        ExcludedRow(
            symbol=df.at[i, "symbol"],
            key=_format_key(df.loc[i], pk_columns),
            reason=QualityViolation(reason.at[i]),
            detail=_DETAIL_MESSAGES[QualityViolation(reason.at[i])],
        )
        for i in df.index[excluded_mask]
    )
    accepted = frame.reset_index(drop=True).loc[~excluded_mask].reset_index(drop=True)
    return accepted, excluded_rows
