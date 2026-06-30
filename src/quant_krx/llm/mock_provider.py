from __future__ import annotations


class MockProvider:
    """테스트/dry-run용 Mock LLM 제공자."""

    def __init__(self, response: str | None = None):
        self._response = response

    @property
    def provider_name(self) -> str:
        return "mock"

    def complete(self, prompt: str) -> str:
        if self._response is not None:
            return self._response
        # 프롬프트에서 종목 정보 추출하여 그럴듯한 mock 응답 생성
        return """### 📊 팩트 (Fact)
퀀트 모델이 산출한 백테스트 지표를 기반으로 분석합니다. [Mock 응답]

### 🔍 추론 (Inference)
이 분석은 Mock LLM이 생성한 테스트용 응답입니다. 실제 LLM 통합 전 파이프라인 검증 목적입니다.

### 💡 권고 (Recommendation)
이 리포트는 투자 권유가 아닙니다. Mock 모드에서는 실제 LLM 분석이 제공되지 않습니다.
최종 투자 결정은 사용자 본인이 내립니다."""
