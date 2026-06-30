import pytest
import os
from quant_krx.llm import LLMProvider, MockProvider, create_provider
from quant_krx.llm.anthropic_provider import AnthropicProvider


def test_mock_provider_complete():
    provider = MockProvider()
    result = provider.complete("test prompt")
    assert isinstance(result, str)
    assert len(result) > 0


def test_mock_provider_custom_response():
    provider = MockProvider(response="custom response")
    assert provider.complete("any prompt") == "custom response"


def test_mock_provider_name():
    provider = MockProvider()
    assert provider.provider_name == "mock"


def test_mock_implements_protocol():
    provider = MockProvider()
    assert isinstance(provider, LLMProvider)


def test_create_provider_mock_flag():
    provider = create_provider(mock=True)
    assert isinstance(provider, MockProvider)


def test_create_provider_env_var(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    provider = create_provider()
    assert isinstance(provider, MockProvider)


def test_create_provider_env_var_false(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    # anthropic provider 생성 시 실제 API 호출 없음 (인스턴스만 생성)
    provider = create_provider(provider="anthropic", mock=False)
    assert isinstance(provider, AnthropicProvider)


def test_create_provider_unknown_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(provider="unknown_llm", mock=False)


def test_anthropic_provider_name(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    provider = AnthropicProvider(api_key="sk-ant-test-key", model="claude-haiku-4-5-20251001")
    assert "anthropic" in provider.provider_name
    assert "haiku" in provider.provider_name
