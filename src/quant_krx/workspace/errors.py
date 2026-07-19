from __future__ import annotations

from collections.abc import Iterable


def not_found_hint(available_ids: Iterable[str]) -> str:
    """미존재 id 오류 메시지에 덧붙이는 "사용 가능한 id" 행동 힌트(공통 원칙 7, TR-R03-024)."""
    ids = sorted(available_ids)
    return f" 사용 가능한 id: {', '.join(ids)}" if ids else " (등록된 항목 없음)"


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


class EmptyOhlcvError(EvaluationError):
    """OHLCV가 0행 — 해당 종목이 선택한 데이터소스에 없거나 기간 밖일 때(vectorbt 크래시 방어)."""

    def __init__(self, symbol: str):
        super().__init__(
            f"'{symbol}' 종목의 OHLCV 데이터가 없습니다"
            "(데이터소스에 해당 종목이 없거나 조회 기간 밖일 수 있습니다)"
        )
        self.symbol = symbol
