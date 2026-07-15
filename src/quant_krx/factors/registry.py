from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import Factor
from .errors import (
    DuplicateFactorError,
    FactorMetadataMismatchError,
    ParamValidationError,
    UnknownFactorError,
)
from .metadata import FactorCategory, FactorMetadata

_REGISTRY: dict[str, Callable[..., Factor]] = {}
_METADATA: dict[str, FactorMetadata] = {}


def register_factor(factor_id: str, constructor: Callable[..., Factor]) -> None:
    """팩터 생성자를 등록한다. 중복 id는 DuplicateFactorError.

    등록 시점에 기본 인스턴스를 1회 생성해 FactorMetadata를 캐시한다(데이터 무관 결정성, FR-11).
    """
    if factor_id in _REGISTRY:
        raise DuplicateFactorError(factor_id)
    default_instance = constructor()
    if default_instance.metadata.id != factor_id:
        raise FactorMetadataMismatchError(factor_id, default_instance.metadata.id)
    _REGISTRY[factor_id] = constructor
    _METADATA[factor_id] = default_instance.metadata


def list_factors(category: FactorCategory | str | None = None) -> tuple[FactorMetadata, ...]:
    """등록된 팩터 메타데이터를 id 오름차순으로 반환. category 지정 시 필터."""
    items = sorted(_METADATA.values(), key=lambda m: m.id)
    if category is None:
        return tuple(items)
    cat_value = category.value if isinstance(category, FactorCategory) else category
    return tuple(m for m in items if m.category.value == cat_value)


def _validate_param_spec(factor_id: str, metadata: FactorMetadata, params: dict[str, Any]) -> None:
    spec_by_name = {p.name: p for p in metadata.params}
    reasons: list[str] = []
    for key, value in params.items():
        spec = spec_by_name.get(key)
        if spec is None:
            allowed = ", ".join(sorted(spec_by_name)) or "(파라미터 없음)"
            reasons.append(f"미지의 파라미터 '{key}' (허용: {allowed})")
            continue
        is_int_for_float = spec.type is float and isinstance(value, int)
        if not isinstance(value, spec.type) and not is_int_for_float:
            reasons.append(
                f"'{key}'는 {spec.type.__name__} 타입이어야 합니다(입력: {type(value).__name__})"
            )
            continue
        if spec.min is not None and value < spec.min:
            reasons.append(f"'{key}'는 {spec.min} 이상이어야 합니다(입력: {value})")
        if spec.max is not None and value > spec.max:
            reasons.append(f"'{key}'는 {spec.max} 이하여야 합니다(입력: {value})")
        if spec.choices is not None and value not in spec.choices:
            reasons.append(f"'{key}'는 {spec.choices} 중 하나여야 합니다(입력: {value})")
    if reasons:
        raise ParamValidationError(factor_id, tuple(reasons))


def get_factor(factor_id: str, **params: Any) -> Factor:
    """파라미터 오버라이드를 적용한 팩터 인스턴스를 생성한다 (D1).

    검증 순서: (1) id 존재 (2) 파라미터 키/타입/범위/choices (3) validate_params 교차 제약 훅.
    """
    constructor = _REGISTRY.get(factor_id)
    if constructor is None:
        raise UnknownFactorError(factor_id, tuple(_REGISTRY.keys()))

    metadata = _METADATA[factor_id]
    _validate_param_spec(factor_id, metadata, params)

    instance = constructor(**params)

    validate_params = getattr(instance, "validate_params", None)
    if validate_params is not None:
        resolved = {p.name: getattr(instance, p.name) for p in metadata.params}
        reasons = validate_params(resolved)
        if reasons:
            raise ParamValidationError(factor_id, tuple(reasons))

    return instance
