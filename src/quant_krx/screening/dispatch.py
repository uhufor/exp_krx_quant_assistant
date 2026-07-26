from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_krx.screening.definition import (
    Composition,
    Node,
    Predicate,
    RankPredicate,
    WindowPredicate,
)
from quant_krx.screening.errors import MalformedDefinitionError

_NODE_DISPATCH: dict[str, type] = {
    "predicate": Predicate,
    "window_predicate": WindowPredicate,
    "rank_predicate": RankPredicate,
    "composition": Composition,
}


def node_from_dict(d: Mapping[str, Any]) -> Node:
    """screening 전용 노드 디스패치 — predicate/window_predicate/rank_predicate/composition 4종.

    rule.definition.node_from_dict는 window/rank 태그를 모르므로 재사용 불가(독립 디스패치, INV-2).
    """
    node_tag = d.get("node")
    if node_tag is None:
        raise MalformedDefinitionError("노드에 'node' 태그가 필요합니다")
    node_cls = _NODE_DISPATCH.get(node_tag)
    if node_cls is None:
        raise MalformedDefinitionError(
            f"미지의 node 태그 '{node_tag}'(허용: {sorted(_NODE_DISPATCH)})"
        )
    return node_cls.from_dict(d)
