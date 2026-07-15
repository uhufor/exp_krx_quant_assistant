from __future__ import annotations

from dataclasses import dataclass

import pytest

from quant_krx._jsonnorm import (
    CanonicalEq,
    MalformedDefinitionError,
    ValidationResult,
    canonical_json,
    normalize_mapping,
    normalize_value,
)


def test_canonical_json_distinguishes_int_and_float() -> None:
    assert canonical_json({"a": 30}) != canonical_json({"a": 30.0})
    assert canonical_json({"a": 30}) == '{"a":30}'
    assert canonical_json({"a": 30.0}) == '{"a":30.0}'


def test_canonical_json_sorts_keys_deterministically() -> None:
    first = canonical_json({"b": 1, "a": 2})
    second = canonical_json({"a": 2, "b": 1})
    assert first == second == '{"a":2,"b":1}'


def test_normalize_mapping_converts_nested_tuple_to_list() -> None:
    result = normalize_mapping({"x": (1, 2, (3, 4))})
    assert result == {"x": [1, 2, [3, 4]]}


def test_normalize_mapping_rejects_non_str_key() -> None:
    with pytest.raises(MalformedDefinitionError):
        normalize_mapping({1: "a"})  # type: ignore[dict-item]


def test_normalize_value_rejects_unsupported_type() -> None:
    with pytest.raises(MalformedDefinitionError):
        normalize_value({1, 2, 3})


def test_normalize_mapping_allows_bool_scalar() -> None:
    assert normalize_mapping({"flag": True}) == {"flag": True}


@dataclass(frozen=True, eq=False)
class _Stub(CanonicalEq):
    value: object

    def to_dict(self) -> dict:
        return {"value": self.value}


def test_canonical_eq_distinguishes_int_and_float_constants() -> None:
    assert {_Stub(30), _Stub(30.0)} == {_Stub(30), _Stub(30.0)}
    assert len({_Stub(30), _Stub(30.0)}) == 2


def test_canonical_eq_equal_values_are_equal_and_same_hash() -> None:
    a, b = _Stub(30), _Stub(30)
    assert a == b
    assert hash(a) == hash(b)


def test_canonical_eq_rejects_other_types() -> None:
    assert _Stub(1) != object()


def test_validation_result_bool_reflects_ok() -> None:
    assert bool(ValidationResult(ok=True))
    assert not bool(ValidationResult(ok=False, errors=("오류",)))
