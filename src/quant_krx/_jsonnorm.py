from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

JSONScalar = int | float | str | bool | None


class DefinitionError(Exception):
    """정의 계층(formula/rule/strategy) 공유 오류 기반 클래스."""


class MalformedDefinitionError(DefinitionError):
    """직렬 구조 위반 — 미지 태그/kind·arity 위반·bool 상수·비-str 키 등.

    생성/from_dict 시점 즉시 raise.
    """


class SchemaVersionError(DefinitionError):
    """본문 schema_version이 코드 버전보다 큰 경우(다운그레이드 차단, REQ-C4)."""


class DefinitionValidationError(DefinitionError):
    """엄격 검증기(validate_*_strict)가 첫 오류에서 발생시키는 예외(REQ-V1)."""


@dataclass(frozen=True)
class ValidationResult:
    """비발생(non-raising) 검증기의 반환 타입 — 전 오류 수집, 순서 결정론(REQ-V1)."""

    ok: bool
    errors: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.ok


def normalize_value(value: Any) -> JSONScalar | list | dict:
    """단일 값을 JSON-native로 재귀 정규화(tuple→list, 스칼라 검증). 위반 시 거부(REQ-C2)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]
    if isinstance(value, Mapping):
        return normalize_mapping(value)
    raise MalformedDefinitionError(
        f"JSON 스칼라(int/float/str/bool/None)·리스트·매핑만 허용됩니다"
        f"(입력 타입: {type(value).__name__})"
    )


def normalize_mapping(mapping: Mapping[str, Any]) -> dict[str, JSONScalar | list | dict]:
    """자유형 매핑(metadata, operand params)을 JSON-native로 정규화한다.

    str 키만 허용(위반 → MalformedDefinitionError), 중첩 tuple→list 재귀 변환,
    값은 JSONScalar 또는 정규화된 list/dict만 허용한다(REQ-C2).
    """
    result: dict[str, JSONScalar | list | dict] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise MalformedDefinitionError(
                f"매핑 키는 str만 허용됩니다(입력 타입: {type(key).__name__})"
            )
        result[key] = normalize_value(value)
    return result


def canonical_json(obj: Mapping[str, Any] | Sequence[Any]) -> str:
    """결정론 canonical 직렬화 — 키 정렬 고정, int/float 타입 보존(30→'30', 30.0→'30.0')."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class CanonicalEq:
    """canonical JSON 표현 기반 __eq__/__hash__ 믹스인(REQ-C5).

    필드 기반 eq는 30==30.0이지만 직렬 표현이 달라 해시 계약이 깨지므로, canonical_json(to_dict())
    동일성으로 판정한다 — 30과 30.0은 서로 다른 정의로 취급된다(set 크기 2).
    """

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other) or not hasattr(other, "to_dict"):
            return False
        return canonical_json(self.to_dict()) == canonical_json(other.to_dict())  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash(canonical_json(self.to_dict()))  # type: ignore[attr-defined]
