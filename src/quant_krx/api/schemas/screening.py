from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from quant_krx.screening.definition import ScreeningCondition


class ScreeningConditionCreate(BaseModel):
    """조건 생성/수정 요청 본문.

    universe/root는 재귀 태그드 유니언(Predicate/Composition/WindowPredicate/RankPredicate,
    FactorOperand/ConstantOperand/FormulaOperand)이라 rules.py/strategies.py 관례와 동일하게
    dict pass-through로 받고 ScreeningCondition.from_dict()(dispatch.py)에 검증을 위임한다
    (Pydantic으로 재귀 스키마를 이중 구현하지 않음, INV-2 — screening 정의는 screening 패키지가
    유일 진실 원천).
    """

    id: str | None = None  # POST(생성) 시 필수, PUT(수정)은 경로 파라미터로 override됨
    name: str
    version: str
    universe: dict[str, Any]
    root: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int | None = None


class ScreeningConditionResponse(BaseModel):
    id: str
    name: str
    version: str
    universe: dict[str, Any]
    root: dict[str, Any]
    metadata: dict[str, Any]
    schema_version: int

    @classmethod
    def from_domain(cls, cond: ScreeningCondition) -> ScreeningConditionResponse:
        return cls(**cond.to_dict())


class ScreeningValidateResult(BaseModel):
    ok: bool
    errors: list[str]


class ScreeningRunRequest(BaseModel):
    as_of: date | None = None  # 생략 시 오늘(서비스 계약과 동일)


class ScreeningUniverseSizeResult(BaseModel):
    condition_id: str
    count: int


class ScreeningRunResultItem(BaseModel):
    symbol: str
    name: str
    market: str  # "KOSPI" | "KOSDAQ" | "" (provider가 판별하지 못한 경우)


class ScreeningRunResult(BaseModel):
    condition_id: str
    as_of: date
    passed: list[ScreeningRunResultItem]
    count: int

    @classmethod
    def from_domain(
        cls, condition_id: str, as_of: date, passed: list[tuple[str, str, str]]
    ) -> ScreeningRunResult:
        items = [ScreeningRunResultItem(symbol=s, name=n, market=m) for s, n, m in passed]
        return cls(condition_id=condition_id, as_of=as_of, passed=items, count=len(items))
