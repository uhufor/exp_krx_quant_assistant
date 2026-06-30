from __future__ import annotations

import os


def create_provider(
    provider: str = "anthropic",
    mock: bool | None = None,
    **kwargs,
):
    """
    LLM 제공자 팩토리.
    LLM_MOCK=true 환경변수 또는 mock=True 인수로 MockProvider 반환.
    """
    from quant_krx.llm.mock_provider import MockProvider

    # Mock 모드 우선순위: 인수 > 환경변수
    env_mock = os.environ.get("LLM_MOCK", "").lower() in ("1", "true", "yes")
    use_mock = mock if mock is not None else env_mock

    if use_mock:
        return MockProvider()

    if provider == "anthropic":
        from quant_krx.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(**kwargs)
    elif provider in ("openai", "openai-compatible"):
        from quant_krx.llm.openai_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider(**kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Use 'anthropic' or 'openai'.")
