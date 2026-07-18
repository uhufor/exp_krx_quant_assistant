from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from quant_krx._jsonnorm import MalformedDefinitionError
from quant_krx.api.deps import get_workspace_service
from quant_krx.api.errors import NotFoundError
from quant_krx.workspace.errors import not_found_hint
from quant_krx.workspace.service import WorkspaceService

router = APIRouter()


def _require(body: dict[str, str], key: str) -> str:
    value = body.get(key)
    if not value:
        raise MalformedDefinitionError(f"필수 필드 누락: '{key}'")
    return value


@router.get("")
def list_templates(svc: WorkspaceService = Depends(get_workspace_service)) -> list[dict[str, Any]]:
    return [
        {"template_id": t.template_id, "origin": t.origin, "name": t.name}
        for t in svc.list_templates()
    ]


@router.get("/{template_id}")
def get_template(
    template_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, Any]:
    bundle = svc.get_template(template_id)
    if bundle is None:
        hint = not_found_hint(t.template_id for t in svc.list_templates())
        raise NotFoundError(f"템플릿 '{template_id}'을(를) 찾을 수 없습니다.{hint}")
    return bundle.to_dict()


@router.post("/from/{template_id}", status_code=201)
def create_from_template(
    template_id: str,
    body: dict[str, str],
    svc: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """템플릿 복제로 신규 전략 생성(PRD CRUD AC4). body: {"new_id": "..."}"""
    new_id = _require(body, "new_id")
    defn = svc.create_from_template(template_id, new_id, now=datetime.now())
    return defn.to_dict()


@router.post("", status_code=201)
def save_as_template(
    body: dict[str, str], svc: WorkspaceService = Depends(get_workspace_service)
) -> dict[str, str]:
    """기존 전략을 사용자 Template로 저장. body: {"strategy_id": "...", "template_id": "..."}"""
    strategy_id = _require(body, "strategy_id")
    template_id = _require(body, "template_id")
    svc.save_as_template(strategy_id, template_id, now=datetime.now())
    return {"template_id": template_id}


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: str, svc: WorkspaceService = Depends(get_workspace_service)
) -> None:
    svc.delete_template(template_id)  # Built-in 삭제 시도 -> WorkspaceError -> 409
