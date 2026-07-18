from __future__ import annotations

from typing import Any, TypeVar

from quant_krx._jsonnorm import MalformedDefinitionError

T = TypeVar("T")


def from_dict_safe(cls: type[T], body: dict[str, Any]) -> T:
    """cls.from_dict(body)를 호출하되 필수 필드 누락(KeyError)을 정의 오류로 정규화한다.

    CLI(strategy_edit_cmd 등)가 KeyError를 DefinitionError와 함께 입력 오류로 취급하는
    관례(__main__.py)와 동일하게, API도 KeyError를 MalformedDefinitionError(DefinitionError
    하위)로 승격해 단일 오류 핸들러(api/errors.py)로 400 응답을 낸다.
    """
    try:
        return cls.from_dict(body)  # type: ignore[attr-defined]
    except KeyError as e:
        raise MalformedDefinitionError(f"필수 필드 누락: {e}") from e
