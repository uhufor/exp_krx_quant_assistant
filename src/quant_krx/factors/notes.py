from __future__ import annotations

from enum import Enum

import pandas as pd


class FactorNote(str, Enum):
    MISSING_INPUT = "missing_input"
    NON_POSITIVE_DENOMINATOR = "non_positive_denominator"
    ZERO_DENOMINATOR = "zero_denominator"
    INSUFFICIENT_HISTORY = "insufficient_history"


def attach_note(df: pd.DataFrame, column: str, note: FactorNote) -> None:
    """반환 프레임의 attrs['notes'][column]에 결측 사유를 부착(컬럼 단위 단일 사유)."""
    notes = df.attrs.setdefault("notes", {})
    notes[column] = note


def get_factor_notes(df: pd.DataFrame) -> dict[str, FactorNote]:
    """결측 사유 유일 접근자. attrs['notes'] 사본 반환(없으면 빈 dict)."""
    return dict(df.attrs.get("notes", {}))


def missing_input_frame(index: pd.Index, columns: tuple[str, ...]) -> pd.DataFrame:
    """필요 데이터 프레임 부재 시 degrade 응답 (TR-R01-007).

    예외 없이 전 구간 NaN + MISSING_INPUT을 부착한 DataFrame을 반환한다.
    """
    result = pd.DataFrame(index=index, columns=list(columns), dtype="float64")
    for col in columns:
        attach_note(result, col, FactorNote.MISSING_INPUT)
    return result


def mark_if_nan(df: pd.DataFrame, column: str, note: FactorNote) -> pd.DataFrame:
    """column에 NaN이 하나라도 있으면 해당 컬럼에 note를 부착한다(밸류에이션/재무 카탈로그 공용)."""
    if df[column].isna().any():
        attach_note(df, column, note)
    return df
