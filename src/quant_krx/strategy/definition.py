from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from quant_krx._jsonnorm import CanonicalEq, normalize_mapping
from quant_krx.strategy.errors import MalformedDefinitionError, SchemaVersionError

SCHEMA_VERSION = 2  # v2: portfolio 슬롯 additive 추가(P1)

_KRX_SYMBOL_RE = re.compile(r"^\d{6}$")

# 리밸런싱 주기 — 각 구간의 첫 거래일에만 비중을 재조정한다(사용자 확정: "리밸런싱 시점에만" 거래).
REBALANCE_FREQUENCIES = ("weekly", "monthly", "quarterly")

# 포지션 사이징 — v1은 균등 분배 단일. 열거로 두어 후속 방식(역변동성 등)을 additive로 넓힌다.
SIZING_METHODS = ("equal_weight",)


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
class RankingSpec(CanonicalEq):
    """진입 후보가 max_positions보다 많을 때 무엇으로 줄을 세울지(P1).

    형상은 Rule의 FactorOperand/FormulaOperand와 동형이지만 타입은 자체 정의한다 —
    `strategy/`가 `rule/`을 import하지 않는 현 구조를 유지하기 위함이며, 실제 값 평가는
    두 계층을 모두 아는 `workspace/portfolio.py`가 담당한다(R02는 순수 정의, 평가 없음).
    """

    kind: str  # "factor" | "formula"
    factor_id: str = ""
    column: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    formula_id: str = ""
    descending: bool = True  # True면 값이 큰 종목이 우선(예: ROE 상위)

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", normalize_mapping(dict(self.params)))
        if self.kind == "factor":
            if not self.factor_id or not self.column:
                raise MalformedDefinitionError(
                    "ranking.kind='factor'에는 factor_id와 column이 필요합니다"
                )
            if self.formula_id:
                raise MalformedDefinitionError(
                    "ranking.kind='factor'에는 formula_id를 지정할 수 없습니다"
                )
        elif self.kind == "formula":
            if not self.formula_id:
                raise MalformedDefinitionError("ranking.kind='formula'에는 formula_id가 필요합니다")
            if self.factor_id or self.column or self.params:
                raise MalformedDefinitionError(
                    "ranking.kind='formula'에는 factor_id/column/params를 지정할 수 없습니다"
                )
        else:
            raise MalformedDefinitionError(
                f"미지의 ranking.kind '{self.kind}'(허용: factor, formula)"
            )

    def to_dict(self) -> dict[str, Any]:
        if self.kind == "factor":
            return {
                "kind": "factor",
                "factor_id": self.factor_id,
                "column": self.column,
                "params": dict(self.params),
                "descending": self.descending,
            }
        return {"kind": "formula", "formula_id": self.formula_id, "descending": self.descending}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RankingSpec:
        kind = d.get("kind")
        if kind == "factor":
            return cls(
                kind="factor",
                factor_id=d.get("factor_id", ""),
                column=d.get("column", ""),
                params=d.get("params", {}),
                descending=bool(d.get("descending", True)),
            )
        if kind == "formula":
            return cls(
                kind="formula",
                formula_id=d.get("formula_id", ""),
                descending=bool(d.get("descending", True)),
            )
        raise MalformedDefinitionError(f"미지의 ranking.kind '{kind}'(허용: factor, formula)")


@dataclass(frozen=True, eq=False)
class PortfolioPolicy(CanonicalEq):
    """포트폴리오 백테스트 정책(P1) — 이 슬롯이 있으면 자본 공유 다종목 모드로 실행된다.

    부재(None)면 기존 종목별 독립 백테스트가 그대로 수행된다(하위호환).
    D5 원칙에 따라 여기 선언된 필드는 전부 실행 의미를 가진다.
    """

    max_positions: int
    rebalance: str = "monthly"
    sizing: str = "equal_weight"
    initial_cash: float = 10_000_000.0
    ranking: RankingSpec | None = None

    def __post_init__(self) -> None:
        if self.max_positions < 1:
            raise MalformedDefinitionError(
                f"max_positions는 1 이상이어야 합니다(입력: {self.max_positions})"
            )
        if self.rebalance not in REBALANCE_FREQUENCIES:
            raise MalformedDefinitionError(
                f"미지의 rebalance '{self.rebalance}'(허용: {list(REBALANCE_FREQUENCIES)})"
            )
        if self.sizing not in SIZING_METHODS:
            raise MalformedDefinitionError(
                f"미지의 sizing '{self.sizing}'(허용: {list(SIZING_METHODS)})"
            )
        if self.initial_cash <= 0:
            raise MalformedDefinitionError(
                f"initial_cash는 양수여야 합니다(입력: {self.initial_cash})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_positions": self.max_positions,
            "rebalance": self.rebalance,
            "sizing": self.sizing,
            "initial_cash": self.initial_cash,
            "ranking": self.ranking.to_dict() if self.ranking is not None else None,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PortfolioPolicy:
        unknown = set(d.keys()) - {
            "max_positions", "rebalance", "sizing", "initial_cash", "ranking"
        }
        if unknown:
            raise MalformedDefinitionError(f"미지의 portfolio 필드: {sorted(unknown)}")
        if "max_positions" not in d:
            raise MalformedDefinitionError("portfolio에는 max_positions가 필요합니다")
        ranking_raw = d.get("ranking")
        return cls(
            max_positions=int(d["max_positions"]),
            rebalance=d.get("rebalance", "monthly"),
            sizing=d.get("sizing", "equal_weight"),
            initial_cash=float(d.get("initial_cash", 10_000_000.0)),
            ranking=RankingSpec.from_dict(ranking_raw) if ranking_raw is not None else None,
        )


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
    portfolio: PortfolioPolicy | None = None  # v2 additive — None이면 종목별 독립 백테스트

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
            "portfolio": self.portfolio.to_dict() if self.portfolio is not None else None,
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
        portfolio_raw = d.get("portfolio")
        portfolio = (
            PortfolioPolicy.from_dict(portfolio_raw) if portfolio_raw is not None else None
        )
        return cls(
            id=d["id"],
            name=d["name"],
            version=d["version"],
            factor_refs=tuple(FactorRef.from_dict(fr) for fr in d["factor_refs"]),
            universe=Universe.from_dict(d.get("universe", {})),
            rule=rule,
            metadata=d.get("metadata", {}),
            schema_version=schema_version,
            portfolio=portfolio,
        )
