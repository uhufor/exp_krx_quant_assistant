from __future__ import annotations


class FactorError(Exception):
    """팩터 계층 오류 기반 클래스."""


class UnknownFactorError(FactorError):
    """미존재 팩터 id 조회."""

    def __init__(self, factor_id: str, available_ids: tuple[str, ...]):
        available = ", ".join(sorted(available_ids)) or "(등록된 팩터 없음)"
        super().__init__(
            f"팩터 '{factor_id}'를 찾을 수 없습니다. 사용 가능한 id: {available}"
        )
        self.factor_id = factor_id
        self.available_ids = available_ids


class DuplicateFactorError(FactorError):
    """중복 id 등록."""

    def __init__(self, factor_id: str):
        super().__init__(
            f"팩터 id '{factor_id}'가 이미 등록되어 있습니다. 중복 등록은 허용되지 않습니다."
        )
        self.factor_id = factor_id


class ParamValidationError(FactorError):
    """파라미터 범위/타입/교차 제약 위반."""

    def __init__(self, factor_id: str, reasons: tuple[str, ...]):
        detail = "; ".join(reasons) if reasons else "알 수 없는 파라미터 오류"
        super().__init__(f"팩터 '{factor_id}' 파라미터 검증 실패: {detail}")
        self.factor_id = factor_id
        self.reasons = reasons


class FactorMetadataMismatchError(FactorError):
    """register_factor 인자 id와 생성 인스턴스 metadata.id 불일치."""

    def __init__(self, registered_id: str, metadata_id: str):
        super().__init__(
            f"register_factor('{registered_id}', ...)의 인자 id와 "
            f"생성 인스턴스의 metadata.id('{metadata_id}')가 일치하지 않습니다."
        )
