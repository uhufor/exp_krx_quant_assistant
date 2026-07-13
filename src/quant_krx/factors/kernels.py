from __future__ import annotations

import numpy as np
import pandas as pd


def safe_divide_positive(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """분모 <= 0이면 NaN (NON_POSITIVE_DENOMINATOR 사유의 산식 배선)."""
    result = numerator / denominator
    return result.where(denominator > 0, np.nan)


def safe_divide_nonzero(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """분모 == 0이면 NaN (ZERO_DENOMINATOR 사유의 산식 배선). 음수 분모는 허용."""
    result = numerator / denominator
    return result.where(denominator != 0, np.nan)


def per_kernel(close: pd.Series, eps: pd.Series) -> pd.Series:
    """peg 등 파생 팩터가 재사용하는 PER 산식 단일 원천 (TR-R01-017)."""
    return safe_divide_positive(close, eps)


def step_growth(values: pd.Series) -> pd.Series:
    """스텝함수(공시 갱신 전까지 상수)의 '직전 상이한 스텝 값 대비 증가율'.

    스텝 갱신 시점에만 값이 갱신되고 그 사이 구간은 직전 성장률을 유지한다.
    NaN 조건: 첫 스텝 이전(직전 스텝 없음) 또는 직전 스텝 <= 0.
    입력을 변조하지 않는다(새 Series 반환).
    """
    prev_step = values.shift(1)
    is_change = values.ne(prev_step) & values.notna()

    valid_change = is_change & prev_step.notna() & (prev_step > 0)
    growth_at_change = pd.Series(np.nan, index=values.index, dtype="float64")
    growth_at_change.loc[valid_change] = (
        values.loc[valid_change] - prev_step.loc[valid_change]
    ) / prev_step.loc[valid_change]

    change_only = growth_at_change.where(is_change)
    group_id = is_change.cumsum()
    return change_only.groupby(group_id).transform(lambda s: s.ffill())


def eps_growth_kernel(eps: pd.Series) -> pd.Series:
    """peg 등 파생 팩터가 재사용하는 eps_growth 산식 단일 원천 (TR-R01-017)."""
    return step_growth(eps)


def quarterly_yoy_growth(unified_sorted: pd.DataFrame, column: str) -> pd.Series:
    """(fiscal_year, fiscal_quarter) 오름차순 정렬된 단일계열 재무 프레임에서
    전년 동기 분기(4분기 전) 대비 증가율: (Q_t - Q_t-4) / Q_t-4.
    NaN 조건: Q_t-4 <= 0 또는 부재(4개 분기 미만 이력 — INSUFFICIENT_HISTORY 배선은 호출자 책임).

    분기 연속성을 전제한다(shift(4) 기준). 결측 분기가 있는 실데이터(DART 연동, §4.7
    Deferred)를 다룰 때는 (fiscal_year, fiscal_quarter) 명시 조인으로 대체해야 한다.
    """
    values = unified_sorted[column]
    prior = values.shift(4)
    growth = (values - prior) / prior
    return growth.where(prior > 0, np.nan)
