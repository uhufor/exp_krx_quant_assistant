from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from quant_krx.factors.metadata import FactorMetadata, ParamSpec


class ParamSpecOut(BaseModel):
    name: str
    type: str
    default: int | float
    description: str
    min: int | float | None = None
    max: int | float | None = None
    choices: tuple[int | float, ...] | None = None

    @classmethod
    def from_domain(cls, spec: ParamSpec) -> ParamSpecOut:
        return cls(
            name=spec.name,
            type=spec.type.__name__,
            default=spec.default,
            description=spec.description,
            min=spec.min,
            max=spec.max,
            choices=spec.choices,
        )


class FactorMetadataOut(BaseModel):
    id: str
    display_name: str
    category: str
    description: str
    params: list[ParamSpecOut]
    output: tuple[str, ...]
    required_data: tuple[str, ...]

    @classmethod
    def from_domain(cls, metadata: FactorMetadata) -> FactorMetadataOut:
        return cls(
            id=metadata.id,
            display_name=metadata.display_name,
            category=metadata.category.value,
            description=metadata.description,
            params=[ParamSpecOut.from_domain(p) for p in metadata.params],
            output=metadata.output,
            required_data=metadata.required_data,
        )


class FactorDetailOut(BaseModel):
    """카탈로그 메타데이터 + 지정 파라미터로 생성한 인스턴스 요약(show-factor 상당)."""

    metadata: FactorMetadataOut
    resolved_params: dict[str, Any]

    @classmethod
    def from_domain(
        cls, metadata: FactorMetadata, resolved_params: dict[str, Any]
    ) -> FactorDetailOut:
        out_metadata = FactorMetadataOut.from_domain(metadata)
        return cls(metadata=out_metadata, resolved_params=resolved_params)
