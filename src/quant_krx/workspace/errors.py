from __future__ import annotations


class WorkspaceError(Exception):
    """파사드 기반 오류 — 활성화 전제·활성 참조 보호·Template 충돌·Import 충돌(PRD-R03 §4/§8/§9)."""


class EvaluationError(WorkspaceError):
    """평가·데이터 계약의 실행 시점 실패(전략×종목 격리 단위, PRD-R03 §5.5/§7)."""


class MissingDataError(EvaluationError):
    """required_data 미충족 — 누락 프레임 종류 + 이를 요구한 factor/formula id 힌트(FR-09)."""

    def __init__(self, kind: str, required_by: tuple[str, ...]):
        ids = ", ".join(required_by) or "(알 수 없음)"
        super().__init__(f"데이터 계약 미충족: '{kind}' 프레임이 없습니다(요구: {ids})")
        self.kind = kind
        self.required_by = required_by
