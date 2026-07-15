from __future__ import annotations

import numpy as np
import pandas as pd

_BINARY_OPS = {"+", "-", "*", "/"}
_COMPARISON_OPS = {">", ">=", "<", "<=", "==", "!="}
_CROSS_DIRECTIONS = {"crosses_above", "crosses_below"}


def align(series: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """기준 인덱스로 정렬만 수행한다(보간·ffill 없음). 결측 구간은 NaN(FR-08)."""
    return series.reindex(index)


def broadcast(value: float, index: pd.DatetimeIndex) -> pd.Series:
    """스칼라 상수를 기준 인덱스 Series로 브로드캐스트(스칼라 .shift 크래시 구조적 차단)."""
    return pd.Series(value, index=index, dtype="float64")


def binary_arith(op: str, left: pd.Series, right: pd.Series) -> pd.Series:
    """이항 산술 — NaN 전파, div0 → NaN(무예외)."""
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        result = left / right
        return result.where(right != 0, np.nan)
    raise ValueError(f"미지의 이항 연산자 '{op}'(허용: {sorted(_BINARY_OPS)})")


def compare(op: str, left: pd.Series, right: pd.Series) -> pd.Series:
    """비교 — 불리언화 직전 NaN → False(단일 강제점)."""
    if op not in _COMPARISON_OPS:
        raise ValueError(f"미지의 비교 연산자 '{op}'(허용: {sorted(_COMPARISON_OPS)})")
    ops = {
        ">": left.gt(right),
        ">=": left.ge(right),
        "<": left.lt(right),
        "<=": left.le(right),
        "==": left.eq(right),
        "!=": left.ne(right),
    }
    valid = left.notna() & right.notna()
    return (ops[op] & valid).astype(bool)


def crosses(direction: str, left: pd.Series, right: pd.Series) -> pd.Series:
    """교차 — crosses_above=(l>r)&(l.shift(1)<=r.shift(1)); below 대칭.

    shift 첫 원소는 NaN 비교이므로 False.
    """
    if direction not in _CROSS_DIRECTIONS:
        raise ValueError(f"미지의 교차 방향 '{direction}'(허용: {sorted(_CROSS_DIRECTIONS)})")
    prev_left = left.shift(1)
    prev_right = right.shift(1)
    if direction == "crosses_above":
        now_cond = left > right
        prev_cond = prev_left <= prev_right
    else:
        now_cond = left < right
        prev_cond = prev_left >= prev_right
    valid = left.notna() & right.notna() & prev_left.notna() & prev_right.notna()
    return (now_cond & prev_cond & valid).astype(bool)
