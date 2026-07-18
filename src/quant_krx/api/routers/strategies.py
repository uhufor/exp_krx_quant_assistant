from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from quant_krx.api.deps import get_workspace_service
from quant_krx.api.errors import NotFoundError
from quant_krx.api.schemas._util import from_dict_safe
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.workspace.errors import not_found_hint
from quant_krx.workspace.service import WorkspaceService
from quant_krx.workspace.templates import StrategyBundle

router = APIRouter()


# --- 정적 경로(list/active/validate/import)를 동적 {strategy_id} 경로보다 먼저 등록 ---


@router.get("")
def list_strategies(svc: WorkspaceService = Depends(get_workspace_service)) -> list[dict[str, Any]]:
    return [d.to_dict() for d in svc.list_strategies()]


@router.get("/active")
def list_active(svc: WorkspaceService = Depends(get_workspace_service)) -> list[str]:
    return list(svc.list_active())


@router.post("/validate")
def validate_strategy_draft(
    body: dict[str, Any], svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    """저장 전 실시간 검증(PRD CRUD AC2) — validate_strategy 조합 로직 그대로 재사용(TR-GUI-006)."""
    defn = from_dict_safe(StrategyDefinition, {**body, "id": body.get("id") or "draft_preview"})
    result = svc.validate_strategy(defn)
    return {"ok": result.ok, "errors": list(result.errors)}


@router.post("/import", status_code=201)
def import_strategy(
    body: dict[str, Any],
    on_conflict: Literal["reject", "overwrite"] = Query(default="reject"),
    svc: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
    bundle = from_dict_safe(StrategyBundle, body)
    svc.import_strategy(bundle, now=datetime.now(), on_conflict=on_conflict)
    return {"strategy_id": bundle.strategy.id}


# --- 동적 {strategy_id} 경로 ---


@router.get("/{strategy_id}")
def get_strategy(
    strategy_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    defn = svc.get_strategy(strategy_id)
    if defn is None:
        hint = not_found_hint(d.id for d in svc.list_strategies())
        raise NotFoundError(f"전략 '{strategy_id}'을(를) 찾을 수 없습니다.{hint}")
    return defn.to_dict()


@router.put("/{strategy_id}")
def upsert_strategy(
    strategy_id: str,
    body: dict[str, Any],
    svc: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    defn = from_dict_safe(StrategyDefinition, {**body, "id": strategy_id})
    svc.upsert_strategy(defn, now=datetime.now())
    return defn.to_dict()


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(
    strategy_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> None:
    svc.delete_strategy(strategy_id)  # 활성 참조 시 WorkspaceError -> 409(api/errors.py)


@router.post("/{strategy_id}/activate")
def activate_strategy(
    strategy_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, bool]:
    svc.activate(strategy_id, now=datetime.now())  # 미존재/미검증/초안 -> WorkspaceError -> 409
    return {"active": True}


@router.post("/{strategy_id}/deactivate")
def deactivate_strategy(
    strategy_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, bool]:
    svc.deactivate(strategy_id, now=datetime.now())
    return {"active": False}


@router.get("/{strategy_id}/export")
def export_strategy(
    strategy_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    bundle = svc.export_strategy(strategy_id)  # 미존재 -> WorkspaceError -> 409
    return bundle.to_dict()
