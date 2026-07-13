from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from quant_krx._jsonnorm import CanonicalEq, normalize_mapping
from quant_krx.strategy.errors import MalformedDefinitionError, SchemaVersionError

SCHEMA_VERSION = 1

_KRX_SYMBOL_RE = re.compile(r"^\d{6}$")


@dataclass(frozen=True, eq=False)
class FactorRef(CanonicalEq):
    factor_id: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", normalize_mapping(dict(self.params)))

    def to_dict(self) -> dict[str, Any]:
        return {"factor_id": self.factor_id, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FactorRef:
        return cls(factor_id=d["factor_id"], params=d.get("params", {}))


@dataclass(frozen=True, eq=False)
class Universe(CanonicalEq):
    symbols: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        invalid = [s for s in self.symbols if not _KRX_SYMBOL_RE.match(s)]
        if invalid:
            raise MalformedDefinitionError(
                f"symbols는 KRX 6자리 숫자 형식이어야 합니다(위반: {invalid})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"symbols": list(self.symbols)}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Universe:
        return cls(symbols=tuple(d.get("symbols", ())))


@dataclass(frozen=True, eq=False)
class RuleBinding(CanonicalEq):
    """rule 슬롯의 roles 단일 형상(D4)을 타입으로 고정 — whitelist fail-closed."""

    entry: tuple[str, ...]
    exit: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.entry) == 0:
            raise MalformedDefinitionError("entry는 비어있지 않아야 합니다(무거래 전략 차단)")
        if len(set(self.entry)) != len(self.entry):
            raise MalformedDefinitionError(f"entry 내 rule id 중복 불가: {self.entry}")
        if len(set(self.exit)) != len(self.exit):
            raise MalformedDefinitionError(f"exit 내 rule id 중복 불가: {self.exit}")

    def to_dict(self) -> dict[str, Any]:
        return {"roles": {"entry": list(self.entry), "exit": list(self.exit)}}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RuleBinding:
        if set(d.keys()) != {"roles"}:
            raise MalformedDefinitionError(
                f"rule 슬롯은 {{'roles': {{...}}}} 형상만 허용됩니다(입력 키: {sorted(d.keys())})"
            )
        roles = d["roles"]
        if not isinstance(roles, Mapping):
            raise MalformedDefinitionError("roles는 매핑이어야 합니다")
        unknown_keys = set(roles.keys()) - {"entry", "exit"}
        if unknown_keys:
            raise MalformedDefinitionError(
                f"미지의 역할 키: {sorted(unknown_keys)}(허용: entry, exit)"
            )
        entry = tuple(roles.get("entry", ()))
        exit_ = tuple(roles.get("exit", ()))
        return cls(entry=entry, exit=exit_)


@dataclass(frozen=True, eq=False)
class StrategyDefinition(CanonicalEq):
    id: str
    name: str
    version: str
    factor_refs: tuple[FactorRef, ...]
    universe: Universe
    rule: RuleBinding | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", normalize_mapping(dict(self.metadata)))
        if len(self.factor_refs) == 0:
            raise MalformedDefinitionError("factor_refs는 최소 1개 이상이어야 합니다")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "factor_refs": [fr.to_dict() for fr in self.factor_refs],
            "universe": self.universe.to_dict(),
            "rule": self.rule.to_dict() if self.rule is not None else None,
            "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> StrategyDefinition:
        schema_version = d.get("schema_version", SCHEMA_VERSION)
        if schema_version > SCHEMA_VERSION:
            raise SchemaVersionError(
                f"StrategyDefinition.schema_version={schema_version}이 현재 코드 버전"
                f"({SCHEMA_VERSION})보다 큽니다(다운그레이드 차단)"
            )
        rule_raw = d.get("rule")
        rule = RuleBinding.from_dict(rule_raw) if rule_raw is not None else None
        return cls(
            id=d["id"],
            name=d["name"],
            version=d["version"],
            factor_refs=tuple(FactorRef.from_dict(fr) for fr in d["factor_refs"]),
            universe=Universe.from_dict(d.get("universe", {})),
            rule=rule,
            metadata=d.get("metadata", {}),
            schema_version=schema_version,
        )
