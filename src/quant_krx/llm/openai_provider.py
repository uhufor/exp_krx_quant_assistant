from __future__ import annotations

import os


class OpenAICompatibleProvider:
    """OpenAI 호환 API 제공자 (OpenAI, LM Studio, Ollama 등)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        max_tokens: int = 1024,
    ):
        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
                base_url=base_url,
            )
        except ImportError:
            raise ImportError("openai 패키지가 설치되어 있지 않습니다: pip install openai")
        self._model = model
        self._max_tokens = max_tokens

    @property
    def provider_name(self) -> str:
        return f"openai/{self._model}"

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self._max_tokens,
        )
        return response.choices[0].message.content or ""
