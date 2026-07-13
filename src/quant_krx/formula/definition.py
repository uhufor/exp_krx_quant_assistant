from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from quant_krx._jsonnorm import CanonicalEq, normalize_mapping
from quant_krx.formula.errors import MalformedDefinitionError, SchemaVersionError

SCHEMA_VERSION = 1

_BINARY_OPS = frozenset({"+", "-", "*", "/"})
_UNARY_OPS = frozenset({"neg"})


@dataclass(frozen=True, eq=False)
class FactorOperand(CanonicalEq):
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
            raise MalformedDefinitionError("상수 피연산자 값으로 bool은 허용되지 않습니다(REQ-C6)")
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
    formula_id: str
    column: str = "value"
    kind: ClassVar[str] = "formula"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "formula_id": self.formula_id, "column": self.column}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FormulaOperand:
        return cls(formula_id=d["formula_id"], column=d.get("column", "value"))


@dataclass(frozen=True, eq=False)
class BinaryOp(CanonicalEq):
    op: str
    left: Expr
    right: Expr
    node: ClassVar[str] = "binary"

    def __post_init__(self) -> None:
        if self.op not in _BINARY_OPS:
            raise MalformedDefinitionError(
                f"미지의 이항 연산자 '{self.op}'(허용: {sorted(_BINARY_OPS)})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "op": self.op,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> BinaryOp:
        if "left" not in d or "right" not in d:
            raise MalformedDefinitionError("BinaryOp는 left/right가 모두 필요합니다")
        return cls(op=d["op"], left=expr_from_dict(d["left"]), right=expr_from_dict(d["right"]))


@dataclass(frozen=True, eq=False)
class UnaryOp(CanonicalEq):
    op: str
    operand: Expr
    node: ClassVar[str] = "unary"

    def __post_init__(self) -> None:
        if self.op not in _UNARY_OPS:
            raise MalformedDefinitionError(
                f"미지의 단항 연산자 '{self.op}'(허용: {sorted(_UNARY_OPS)})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"node": self.node, "op": self.op, "operand": self.operand.to_dict()}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> UnaryOp:
        if "operand" not in d:
            raise MalformedDefinitionError("UnaryOp는 operand가 필요합니다")
        return cls(op=d["op"], operand=expr_from_dict(d["operand"]))


Expr = BinaryOp | UnaryOp | FactorOperand | ConstantOperand | FormulaOperand

_NODE_DISPATCH: dict[str, type] = {"binary": BinaryOp, "unary": UnaryOp}
_KIND_DISPATCH: dict[str, type] = {
    "factor": FactorOperand,
    "constant": ConstantOperand,
    "formula": FormulaOperand,
}


def expr_from_dict(d: Mapping[str, Any]) -> Expr:
    """태그 판별 디스패치: 'node'(binary|unary) 우선, 없으면 'kind'(factor|constant|formula).

    미지 태그·태그 부재/중복은 MalformedDefinitionError(REQ-C1/C2).
    """
    has_node = "node" in d
    has_kind = "kind" in d
    if has_node and has_kind:
        raise MalformedDefinitionError("표현식에 'node'와 'kind' 태그가 동시에 존재할 수 없습니다")
    if has_node:
        node_cls = _NODE_DISPATCH.get(d["node"])
        if node_cls is None:
            raise MalformedDefinitionError(
                f"미지의 node 태그 '{d['node']}'(허용: {sorted(_NODE_DISPATCH)})"
            )
        return node_cls.from_dict(d)
    if has_kind:
        kind_cls = _KIND_DISPATCH.get(d["kind"])
        if kind_cls is None:
            raise MalformedDefinitionError(
                f"미지의 kind 태그 '{d['kind']}'(허용: {sorted(_KIND_DISPATCH)})"
            )
        return kind_cls.from_dict(d)
    raise MalformedDefinitionError("표현식에 'node' 또는 'kind' 태그가 필요합니다")


@dataclass(frozen=True, eq=False)
class Formula(CanonicalEq):
    id: str
    name: str
    version: str
    expression: Expr
    output_column: str = "value"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", normalize_mapping(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "expression": self.expression.to_dict(),
            "output_column": self.output_column,
            "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Formula:
        schema_version = d.get("schema_version", SCHEMA_VERSION)
        if schema_version > SCHEMA_VERSION:
            raise SchemaVersionError(
                f"Formula.schema_version={schema_version}이 현재 코드 버전"
                f"({SCHEMA_VERSION})보다 큽니다(다운그레이드 차단)"
            )
        return cls(
            id=d["id"],
            name=d["name"],
            version=d["version"],
            expression=expr_from_dict(d["expression"]),
            output_column=d.get("output_column", "value"),
            metadata=d.get("metadata", {}),
            schema_version=schema_version,
        )
