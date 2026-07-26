from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from quant_krx._jsonnorm import CanonicalEq, normalize_mapping
from quant_krx.screening.errors import (
    MalformedDefinitionError,
    SchemaVersionError,
    UnsupportedFilterError,
)

SCHEMA_VERSION = 1

_COMPARISON_OPS = frozenset({">", ">=", "<", "<=", "==", "!="})
_CROSS_OPS = frozenset({"crosses_above", "crosses_below"})
_PREDICATE_OPS = _COMPARISON_OPS | _CROSS_OPS
_LOGICAL_OPS = frozenset({"AND", "OR", "NOT"})
_RANK_METRICS = frozenset({"asc", "desc"})

# 예약되었으나 아직 미지원인 제외 필터 6종.
_UNSUPPORTED_FILTERS = frozenset(
    {
        "administrative_issue",
        "investment_alert",
        "trading_halt",
        "liquidation_trading",
        "market_alert",
        "unfaithful_disclosure",
    }
)


@dataclass(frozen=True, eq=False)
class FactorOperand(CanonicalEq):
    """screening 패키지 전용 피연산자 — rule/formula 패키지의 동명 클래스와 완전 별개(INV-2)."""

    factor_id: str
    column: str
    params: Mapping[str, Any] = field(default_factory=dict)
    kind: ClassVar[str] = "factor"

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", normalize_mapping(dict(self.params)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "factor_id": self.factor_id,
            "column": self.column,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FactorOperand:
        return cls(factor_id=d["factor_id"], column=d["column"], params=d.get("params", {}))


@dataclass(frozen=True, eq=False)
class ConstantOperand(CanonicalEq):
    value: int | float
    kind: ClassVar[str] = "constant"

    def __post_init__(self) -> None:
        if isinstance(self.value, bool):
            raise MalformedDefinitionError("상수 피연산자 값으로 bool은 허용되지 않습니다")
        if not isinstance(self.value, (int, float)):
            raise MalformedDefinitionError(
                f"상수 피연산자 값은 int/float만 허용됩니다(입력 타입: {type(self.value).__name__})"
            )
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise MalformedDefinitionError("상수 피연산자 값은 유한해야 합니다(nan/inf 거부)")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ConstantOperand:
        return cls(value=d["value"])


@dataclass(frozen=True, eq=False)
class FormulaOperand(CanonicalEq):
    """screening 패키지 전용 피연산자 — formula_id 문자열만 보유(formula 패키지 미참조, INV-2)."""

    formula_id: str
    column: str = "value"
    kind: ClassVar[str] = "formula"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "formula_id": self.formula_id, "column": self.column}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FormulaOperand:
        return cls(formula_id=d["formula_id"], column=d.get("column", "value"))


Operand = FactorOperand | ConstantOperand | FormulaOperand

_OPERAND_DISPATCH: dict[str, type] = {
    "factor": FactorOperand,
    "constant": ConstantOperand,
    "formula": FormulaOperand,
}


def operand_from_dict(d: Mapping[str, Any]) -> Operand:
    kind = d.get("kind")
    if kind is None:
        raise MalformedDefinitionError("피연산자에 'kind' 태그가 필요합니다")
    operand_cls = _OPERAND_DISPATCH.get(kind)
    if operand_cls is None:
        raise MalformedDefinitionError(
            f"미지의 kind 태그 '{kind}'(허용: {sorted(_OPERAND_DISPATCH)})"
        )
    return operand_cls.from_dict(d)


@dataclass(frozen=True, eq=False)
class Predicate(CanonicalEq):
    left: Operand
    operator: str
    right: Operand
    node: ClassVar[str] = "predicate"

    def __post_init__(self) -> None:
        if self.operator not in _PREDICATE_OPS:
            raise MalformedDefinitionError(
                f"미지의 비교 연산자 '{self.operator}'(허용: {sorted(_PREDICATE_OPS)})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "left": self.left.to_dict(),
            "operator": self.operator,
            "right": self.right.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Predicate:
        if "left" not in d or "right" not in d:
            raise MalformedDefinitionError("Predicate는 left/right가 모두 필요합니다")
        return cls(
            left=operand_from_dict(d["left"]),
            operator=d["operator"],
            right=operand_from_dict(d["right"]),
        )


@dataclass(frozen=True, eq=False)
class WindowPredicate(CanonicalEq):
    """내부 노드가 최근 n_bars 구간에서 성립하는지 평가하는 시간창 서술자(screening 신규 노드)."""

    inner: Node
    n_bars: int
    include_current_bar: bool
    node: ClassVar[str] = "window_predicate"

    def __post_init__(self) -> None:
        if isinstance(self.n_bars, bool) or not isinstance(self.n_bars, int):
            raise MalformedDefinitionError(
                f"n_bars는 정수여야 합니다(입력 타입: {type(self.n_bars).__name__})"
            )
        if self.n_bars < 0:
            raise MalformedDefinitionError(f"n_bars는 0 이상이어야 합니다(입력: {self.n_bars})")
        if not isinstance(self.include_current_bar, bool):
            raise MalformedDefinitionError(
                f"include_current_bar는 bool이어야 합니다"
                f"(입력 타입: {type(self.include_current_bar).__name__})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "inner": self.inner.to_dict(),
            "n_bars": self.n_bars,
            "include_current_bar": self.include_current_bar,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> WindowPredicate:
        from quant_krx.screening.dispatch import node_from_dict

        if "inner" not in d:
            raise MalformedDefinitionError("WindowPredicate는 inner가 필요합니다")
        return cls(
            inner=node_from_dict(d["inner"]),
            n_bars=d["n_bars"],
            include_current_bar=d["include_current_bar"],
        )


@dataclass(frozen=True, eq=False)
class RankPredicate(CanonicalEq):
    """팩터 값 기준 상위 top_n 종목만 통과시키는 횡단면 순위 서술자(screening 신규 노드)."""

    factor_id: str
    column: str
    rank_metric: str
    top_n: int
    params: Mapping[str, Any] = field(default_factory=dict)
    node: ClassVar[str] = "rank_predicate"

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", normalize_mapping(dict(self.params)))
        if self.rank_metric not in _RANK_METRICS:
            raise MalformedDefinitionError(
                f"미지의 rank_metric '{self.rank_metric}'(허용: {sorted(_RANK_METRICS)})"
            )
        if isinstance(self.top_n, bool) or not isinstance(self.top_n, int):
            raise MalformedDefinitionError(
                f"top_n은 정수여야 합니다(입력 타입: {type(self.top_n).__name__})"
            )
        if self.top_n < 1:
            raise MalformedDefinitionError(f"top_n은 1 이상이어야 합니다(입력: {self.top_n})")

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "factor_id": self.factor_id,
            "column": self.column,
            "rank_metric": self.rank_metric,
            "top_n": self.top_n,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RankPredicate:
        return cls(
            factor_id=d["factor_id"],
            column=d["column"],
            rank_metric=d["rank_metric"],
            top_n=d["top_n"],
            params=d.get("params", {}),
        )


@dataclass(frozen=True, eq=False)
class Composition(CanonicalEq):
    op: str
    operands: tuple[Node, ...]
    node: ClassVar[str] = "composition"

    def __post_init__(self) -> None:
        if self.op not in _LOGICAL_OPS:
            raise MalformedDefinitionError(
                f"미지의 논리 연산자 '{self.op}'(허용: {sorted(_LOGICAL_OPS)})"
            )
        if self.op in ("AND", "OR") and len(self.operands) < 2:
            raise MalformedDefinitionError(
                f"{self.op}는 피연산자가 2개 이상이어야 합니다(입력: {len(self.operands)}개)"
            )
        if self.op == "NOT" and len(self.operands) != 1:
            raise MalformedDefinitionError(
                f"NOT은 피연산자가 정확히 1개여야 합니다(입력: {len(self.operands)}개)"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "op": self.op,
            "operands": [operand.to_dict() for operand in self.operands],
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Composition:
        from quant_krx.screening.dispatch import node_from_dict

        operands_raw = d.get("operands")
        if operands_raw is None:
            raise MalformedDefinitionError("Composition은 operands가 필요합니다")
        return cls(op=d["op"], operands=tuple(node_from_dict(n) for n in operands_raw))


Node = Predicate | WindowPredicate | RankPredicate | Composition


@dataclass(frozen=True, eq=False)
class ScanUniverse(CanonicalEq):
    market: str = "KRX"
    exclusion_filters: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "exclusion_filters", frozenset(self.exclusion_filters))
        rejected = self.exclusion_filters & _UNSUPPORTED_FILTERS
        if rejected:
            raise UnsupportedFilterError(
                f"미지원 제외 필터가 포함되었습니다: {sorted(rejected)}"
                f"(예약 미지원: {sorted(_UNSUPPORTED_FILTERS)})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"market": self.market, "exclusion_filters": sorted(self.exclusion_filters)}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ScanUniverse:
        return cls(
            market=d.get("market", "KRX"),
            exclusion_filters=frozenset(d.get("exclusion_filters", ())),
        )


@dataclass(frozen=True, eq=False)
class ScreeningCondition(CanonicalEq):
    id: str
    name: str
    version: str
    universe: ScanUniverse
    root: Node
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", normalize_mapping(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "universe": self.universe.to_dict(),
            "root": self.root.to_dict(),
            "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ScreeningCondition:
        from quant_krx.screening.dispatch import node_from_dict

        schema_version = d.get("schema_version", SCHEMA_VERSION)
        if schema_version > SCHEMA_VERSION:
            raise SchemaVersionError(
                f"ScreeningCondition.schema_version={schema_version}이 현재 코드 버전"
                f"({SCHEMA_VERSION})보다 큽니다(다운그레이드 차단)"
            )
        return cls(
            id=d["id"],
            name=d["name"],
            version=d["version"],
            universe=ScanUniverse.from_dict(d["universe"]),
            root=node_from_dict(d["root"]),
            metadata=d.get("metadata", {}),
            schema_version=schema_version,
        )
