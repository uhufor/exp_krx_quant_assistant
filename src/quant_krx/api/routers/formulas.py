from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from quant_krx.api.deps import get_workspace_service
from quant_krx.api.errors import NotFoundError
from quant_krx.api.schemas._util import from_dict_safe
from quant_krx.formula.definition import Formula
from quant_krx.formula.validation import validate_formula
from quant_krx.workspace.errors import not_found_hint
from quant_krx.workspace.service import WorkspaceService

router = APIRouter()


@router.get("")
def list_formulas(svc: WorkspaceService = Depends(get_workspace_service)) -> list[dict[str, Any]]:
    return [f.to_dict() for f in svc.list_formulas()]


@router.get("/{formula_id}")
def get_formula(
    formula_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    formula = svc.get_formula(formula_id)
    if formula is None:
        hint = not_found_hint(f.id for f in svc.list_formulas())
        raise NotFoundError(f"공식 '{formula_id}'을(를) 찾을 수 없습니다.{hint}")
    return formula.to_dict()


@router.put("/{formula_id}")
def upsert_formula(
    formula_id: str, body: dict[str, Any], svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    formula = from_dict_safe(Formula, {**body, "id": formula_id})
    svc.upsert_formula(formula, now=datetime.now())
    return formula.to_dict()


@router.post("/validate")
def validate_formula_draft(
    body: dict[str, Any], svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    """저장 전 실시간 검증(PRD CRUD AC2) — validate_formula 순수 함수 직접 재사용(TR-GUI-006)."""
    formula = from_dict_safe(Formula, {**body, "id": body.get("id") or "draft_preview"})
    result = validate_formula(formula, resolve_formula=svc.get_formula)
    return {"ok": result.ok, "errors": list(result.errors)}


@router.delete("/{formula_id}", status_code=204)
def delete_formula(formula_id: str, svc: WorkspaceService = Depends(get_workspace_service)) -> None:
    svc.delete_formula(formula_id)  # 활성 참조 시 WorkspaceError -> 409(api/errors.py)
