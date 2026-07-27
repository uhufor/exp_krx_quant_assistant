"""백테스트 산출물의 JSON 직렬화 유틸(P3).

원래 `api/schemas/backtest.py`에 있던 순수 변환 함수를 이 계층으로 내렸다 — 실행 이력
영속(`workspace/persistence.py`)과 GUI 응답이 **동일한 직렬화 계약**을 써야 저장된 결과와
방금 실행한 결과가 바이트 단위로 비교 가능하기 때문이다. `api/schemas/backtest.py`는 이
모듈을 재export하므로 기존 import 경로는 그대로 동작한다.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pandas as pd

from quant_krx.quant.base import BacktestMetrics


def to_json_safe(value: Any) -> Any:
    """pandas/numpy 스칼라를 JSON 직렬화 가능한 파이썬 네이티브 값으로 정규화.

    순서 중요: Timestamp(날짜 문자열화) -> NaN/NaT(None) -> numpy 스칼라(.item()) -> passthrough.
    """
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):  # numpy int64/float64/bool_
        return value.item()
    return value


def serialize_metrics(metrics: BacktestMetrics) -> dict[str, Any]:
    return {k: to_json_safe(v) for k, v in dataclasses.asdict(metrics).items()}


def deserialize_metrics(raw: dict[str, Any]) -> BacktestMetrics:
    """serialize_metrics의 역변환 — None(직렬화된 NaN)을 다시 NaN으로 되돌린다.

    `benchmark_note`만 문자열 필드이므로 None -> "" 로 복원하고, 나머지 수치 필드는
    None -> float("nan")으로 되돌려 `math.isnan` 분기(CLI 표 렌더링)가 그대로 동작하게 한다.
    (dataclass가 `from __future__ import annotations` 아래 정의되어 `field.type`이 문자열
    이므로 타입 객체 비교 대신 필드명으로 판정한다.)
    """
    kwargs: dict[str, Any] = {}
    for field in dataclasses.fields(BacktestMetrics):
        value = raw.get(field.name)
        if value is None:
            kwargs[field.name] = "" if field.name == "benchmark_note" else float("nan")
        else:
            kwargs[field.name] = value
    return BacktestMetrics(**kwargs)


def serialize_equity_curve(series: pd.Series) -> list[dict[str, Any]]:
    """DatetimeIndex pd.Series -> [{date, value}] (§5.1 TRD-R01 직렬화 계약)."""
    return [
        {"date": to_json_safe(idx), "value": to_json_safe(val)} for idx, val in series.items()
    ]


def deserialize_equity_curve(raw: list[dict[str, Any]]) -> pd.Series:
    """serialize_equity_curve의 역변환 — DatetimeIndex pd.Series 복원."""
    if not raw:
        return pd.Series(dtype=float)
    index = pd.DatetimeIndex([pd.Timestamp(row["date"]) for row in raw])
    return pd.Series([row["value"] for row in raw], index=index, dtype=float)
