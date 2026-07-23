from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends

from quant_krx.api.deps import get_screening_service
from quant_krx.api.errors import NotFoundError
from quant_krx.api.schemas._util import from_dict_safe
from quant_krx.api.schemas.screening import (
    ScreeningConditionCreate,
    ScreeningConditionResponse,
    ScreeningRunRequest,
    ScreeningRunResult,
    ScreeningUniverseSizeResult,
    ScreeningValidateResult,
)
from quant_krx.screening.definition import ScreeningCondition
from quant_krx.screening.service import ScreeningService
from quant_krx.workspace.errors import not_found_hint

router = APIRouter()


def _get_or_404(svc: ScreeningService, condition_id: str) -> ScreeningCondition:
    cond = svc.get_condition(condition_id)
    if cond is None:
        hint = not_found_hint(c.id for c in svc.list_conditions())
        raise NotFoundError(f"스크리닝 조건 '{condition_id}'을(를) 찾을 수 없습니다.{hint}")
    return cond


@router.get("")
def list_screenings(
    svc: ScreeningService = Depends(get_screening_service),
) -> list[ScreeningConditionResponse]:
    return [ScreeningConditionResponse.from_domain(c) for c in svc.list_conditions()]


@router.get("/{condition_id}")
def get_screening(
    condition_id: str, svc: ScreeningService = Depends(get_screening_service)
) -> ScreeningConditionResponse:
    cond = _get_or_404(svc, condition_id)
    return ScreeningConditionResponse.from_domain(cond)


@router.post("", status_code=201)
def create_screening(
    body: ScreeningConditionCreate, svc: ScreeningService = Depends(get_screening_service)
) -> ScreeningConditionResponse:
    cond = from_dict_safe(ScreeningCondition, body.model_dump(exclude_none=True))
    svc.upsert_condition(cond, now=datetime.now())
    return ScreeningConditionResponse.from_domain(cond)


@router.put("/{condition_id}")
def upsert_screening(
    condition_id: str,
    body: ScreeningConditionCreate,
    svc: ScreeningService = Depends(get_screening_service),
) -> ScreeningConditionResponse:
    payload = {**body.model_dump(exclude_none=True), "id": condition_id}
    cond = from_dict_safe(ScreeningCondition, payload)
    svc.upsert_condition(cond, now=datetime.now())
    return ScreeningConditionResponse.from_domain(cond)


@router.delete("/{condition_id}", status_code=204)
def delete_screening(
    condition_id: str, svc: ScreeningService = Depends(get_screening_service)
) -> None:
    svc.delete_condition(condition_id)


@router.post("/{condition_id}/validate")
def validate_screening(
    condition_id: str, svc: ScreeningService = Depends(get_screening_service)
) -> ScreeningValidateResult:
    cond = _get_or_404(svc, condition_id)
    result = svc.validate_condition(cond)
    return ScreeningValidateResult(ok=result.ok, errors=list(result.errors))


@router.get("/{condition_id}/universe-size")
def get_screening_universe_size(
    condition_id: str, svc: ScreeningService = Depends(get_screening_service)
) -> ScreeningUniverseSizeResult:
    """실행 전 대상 종목수만 빠르게 미리 보여준다(OHLCV·순위 조회 없이 유니버스만 해석)."""
    _get_or_404(svc, condition_id)
    count = svc.count_universe(condition_id)
    return ScreeningUniverseSizeResult(condition_id=condition_id, count=count)


@router.post("/{condition_id}/run")
def run_screening(
    condition_id: str,
    body: ScreeningRunRequest = ScreeningRunRequest(),
    svc: ScreeningService = Depends(get_screening_service),
) -> ScreeningRunResult:
    _get_or_404(svc, condition_id)  # 없는 id는 404(NotFoundError) — service 예외에 위임하지 않음
    as_of = body.as_of or date.today()
    passed = svc.run(condition_id, as_of=as_of)
    return ScreeningRunResult.from_domain(condition_id, as_of, passed)
