from __future__ import annotations


class ScreeningError(Exception):
    """screening 패키지 공통 오류 기반 클래스 — rule.errors를 import하지 않는 독립 정의(INV-2)."""


class MalformedDefinitionError(ScreeningError):
    """직렬 구조 위반 — 미지 태그/kind·arity 위반·bool 상수·비-str 키 등.

    생성/from_dict 시점 즉시 raise.
    """


class SchemaVersionError(ScreeningError):
    """본문 schema_version이 코드 버전보다 큰 경우(다운그레이드 차단)."""


class EmptyUniverseError(ScreeningError):
    """스캔 유니버스가 비어 스크리닝 대상 종목이 하나도 없는 경우."""


class UnsupportedFilterError(ScreeningError):
    """예약되었으나 아직 미지원인 제외 필터가 exclusion_filters에 포함된 경우."""


__all__ = [
    "ScreeningError",
    "MalformedDefinitionError",
    "SchemaVersionError",
    "EmptyUniverseError",
    "UnsupportedFilterError",
]
