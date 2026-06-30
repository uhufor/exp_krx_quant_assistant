from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """LLM 제공자 인터페이스."""

    @property
    def provider_name(self) -> str: ...

    def complete(self, prompt: str) -> str: ...
