from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from quant_krx.api.deps import get_workspace_service
from quant_krx.api.errors import NotFoundError
from quant_krx.api.schemas._util import from_dict_safe
from quant_krx.rule.definition import Rule
from quant_krx.rule.validation import validate_rule
from quant_krx.workspace.errors import not_found_hint
from quant_krx.workspace.service import WorkspaceService

router = APIRouter()


@router.get("")
def list_rules(svc: WorkspaceService = Depends(get_workspace_service)) -> list[dict[str, Any]]:
    return [r.to_dict() for r in svc.list_rules()]


@router.get("/{rule_id}")
def get_rule(
    rule_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    rule = svc.get_rule(rule_id)
    if rule is None:
        hint = not_found_hint(r.id for r in svc.list_rules())
        raise NotFoundError(f"Rule '{rule_id}'을(를) 찾을 수 없습니다.{hint}")
    return rule.to_dict()


@router.put("/{rule_id}")
def upsert_rule(
    rule_id: str, body: dict[str, Any], svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    rule = from_dict_safe(Rule, {**body, "id": rule_id})
    svc.upsert_rule(rule, now=datetime.now())
    return rule.to_dict()


@router.post("/validate")
def validate_rule_draft(
    body: dict[str, Any], svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    """저장 전 실시간 검증(PRD CRUD AC2) — validate_rule 순수 함수 직접 재사용(TR-GUI-006)."""
    rule = from_dict_safe(Rule, {**body, "id": body.get("id") or "draft_preview"})
    result = validate_rule(rule, resolve_formula=svc.get_formula)
    return {"ok": result.ok, "errors": list(result.errors)}


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: str, svc: WorkspaceService = Depends(get_workspace_service)) -> None:
    svc.delete_rule(rule_id)  # 활성 참조 시 WorkspaceError -> 409(api/errors.py)
