from __future__ import annotations

import os


class AnthropicProvider:
    """Anthropic Claude API 제공자."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1024,
    ):
        import anthropic

        self._model = model
        self._max_tokens = max_tokens
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = anthropic.Anthropic(api_key=resolved_key)

    @property
    def provider_name(self) -> str:
        return f"anthropic/{self._model}"

    def complete(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
