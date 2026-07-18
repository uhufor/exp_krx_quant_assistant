from __future__ import annotations

from fastapi import APIRouter, Query

from quant_krx.api.schemas.factor import FactorDetailOut, FactorMetadataOut
from quant_krx.factors.registry import get_factor, list_factors

router = APIRouter()


@router.get("", response_model=list[FactorMetadataOut])
def list_factors_endpoint(category: str | None = Query(default=None)) -> list[FactorMetadataOut]:
    """list-factors CLI 상당 — 읽기 전용(팩터 생성/수정/삭제 없음, PRD Non-Goals)."""
    metadatas = list_factors(category)
    return [FactorMetadataOut.from_domain(m) for m in metadatas]


@router.get("/{factor_id}", response_model=FactorDetailOut)
def get_factor_endpoint(factor_id: str) -> FactorDetailOut:
    """show-factor CLI 상당 — 기본 파라미터로 인스턴스화해 메타데이터+해석된 파라미터를 반환."""
    instance = get_factor(factor_id)  # UnknownFactorError -> 404 (api/errors.py)
    metadata = instance.metadata
    resolved = {p.name: getattr(instance, p.name) for p in metadata.params}
    return FactorDetailOut.from_domain(metadata, resolved)
