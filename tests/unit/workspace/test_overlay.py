from __future__ import annotations

import pytest

from quant_krx.formula.definition import BinaryOp, Formula
from quant_krx.formula.definition import FactorOperand as FormulaFactorOperand
from quant_krx.rule.definition import Composition, ConstantOperand, FactorOperand, Predicate, Rule
from quant_krx.strategy.definition import (
    FactorRef,
    PortfolioPolicy,
    RankingSpec,
    RuleBinding,
    StrategyDefinition,
    Universe,
)
from quant_krx.workspace.overlay import (
    FactorTarget,
    OverlayError,
    apply_overlay,
    expand_grid,
    overlay_resolvers,
    parse_overlay,
)

PER_RULE = Rule(
    id="per_rule", name="per", version="1",
    root=Predicate(FactorOperand("per", "per", {}), "<", ConstantOperand(15.0)),
)
MOM_RULE = Rule(
    id="mom_rule", name="mom", version="1",
    root=Predicate(FactorOperand("momentum", "momentum", {"window": 60}), ">", ConstantOperand(0.0)),
)
COMBO_RULE = Rule(
    id="combo", name="combo", version="1",
    root=Composition(op="AND", operands=(PER_RULE.root, MOM_RULE.root)),
)
_RULES = {r.id: r for r in (PER_RULE, MOM_RULE, COMBO_RULE)}


def _resolve_rule(rule_id: str):
    return _RULES.get(rule_id)


def _resolve_formula(formula_id: str):
    if formula_id != "mom_ratio":
        return None
    return Formula(
        id="mom_ratio", name="ratio", version="1",
        expression=BinaryOp(
            op="/",
            left=FormulaFactorOperand("momentum", "momentum", {"window": 60}),
            right=FormulaFactorOperand("price", "close", {}),
        ),
    )


def _defn(**kwargs) -> StrategyDefinition:
    base = {
        "id": "s1", "name": "s1", "version": "1",
        "factor_refs": (FactorRef("momentum", {"window": 60}), FactorRef("per")),
        "universe": Universe(symbols=("005930",)),
        "rule": RuleBinding(entry=("per_rule",)),
        "portfolio": PortfolioPolicy(max_positions=3),
    }
    base.update(kwargs)
    return StrategyDefinition(**base)


# --- 키 파싱 ---


def test_parses_all_three_address_forms():
    overlay = parse_overlay(
        {
            "portfolio.max_positions": 5,
            "factor.momentum.window": 120,
            "rule.per_rule.threshold": 10,
        }
    )
    assert overlay.portfolio == {"max_positions": 5}
    assert overlay.factor_params == {FactorTarget("momentum", "window"): 120}
    assert overlay.rule_thresholds == {"per_rule": 10.0}


def test_rejects_unknown_key_form():
    with pytest.raises(OverlayError, match="미지의 오버레이 키"):
        parse_overlay({"universe.symbols": ["005930"]})


def test_rejects_unknown_portfolio_field():
    with pytest.raises(OverlayError, match="미지의 portfolio 필드"):
        parse_overlay({"portfolio.leverage": 2})


def test_rejects_non_threshold_rule_suffix():
    with pytest.raises(OverlayError, match="threshold"):
        parse_overlay({"rule.per_rule.operator": "<"})


def test_casts_max_positions_to_int():
    """JSON에서 5.0으로 들어와도 dataclass 검증(정수 비교)을 통과해야 한다."""
    overlay = parse_overlay({"portfolio.max_positions": 5.0})
    assert overlay.portfolio["max_positions"] == 5
    assert isinstance(overlay.portfolio["max_positions"], int)


# --- 그리드 전개 ---


def test_expand_grid_is_deterministic_product():
    combos = expand_grid({"b": [1, 2], "a": ["x"]})
    assert combos == ({"a": "x", "b": 1}, {"a": "x", "b": 2})


def test_empty_grid_yields_single_empty_combo():
    assert expand_grid({}) == ({},)


def test_rejects_empty_value_list():
    with pytest.raises(OverlayError, match="비어있지 않은 목록"):
        expand_grid({"portfolio.max_positions": []})


# --- 정의 오버레이 ---


def test_overlays_portfolio_field():
    defn = apply_overlay(_defn(), parse_overlay({"portfolio.max_positions": 7}))
    assert defn.portfolio.max_positions == 7


def test_rejects_portfolio_overlay_without_policy():
    with pytest.raises(OverlayError, match="portfolio 정책이 없어"):
        apply_overlay(_defn(portfolio=None), parse_overlay({"portfolio.max_positions": 7}))


def test_overlays_factor_refs_params():
    defn = apply_overlay(_defn(), parse_overlay({"factor.momentum.window": 250}))
    by_id = {ref.factor_id: dict(ref.params) for ref in defn.factor_refs}
    assert by_id["momentum"]["window"] == 250
    assert by_id["per"] == {}  # 다른 팩터는 건드리지 않는다


def test_overlays_ranking_params():
    policy = PortfolioPolicy(
        max_positions=3,
        ranking=RankingSpec(kind="factor", factor_id="momentum", column="momentum",
                            params={"window": 60}),
    )
    defn = apply_overlay(_defn(portfolio=policy), parse_overlay({"factor.momentum.window": 250}))
    assert dict(defn.portfolio.ranking.params)["window"] == 250


def test_original_definition_is_not_mutated():
    original = _defn()
    apply_overlay(original, parse_overlay({"portfolio.max_positions": 9,
                                           "factor.momentum.window": 250}))
    assert original.portfolio.max_positions == 3
    assert dict(original.factor_refs[0].params)["window"] == 60


def test_empty_overlay_returns_same_object():
    original = _defn()
    assert apply_overlay(original, parse_overlay({})) is original


# --- 리졸버 오버레이 ---


def test_rewrites_factor_params_inside_rule():
    """실행 시 실제로 쓰이는 파라미터는 rule 피연산자 쪽이다 — 여기가 안 바뀌면 스윕이 무효."""
    resolve_rule, _ = overlay_resolvers(
        parse_overlay({"factor.momentum.window": 250}), _resolve_rule, _resolve_formula
    )
    rule = resolve_rule("mom_rule")
    assert dict(rule.root.left.params)["window"] == 250


def test_rewrites_factor_params_inside_formula():
    _, resolve_formula = overlay_resolvers(
        parse_overlay({"factor.momentum.window": 250}), _resolve_rule, _resolve_formula
    )
    formula = resolve_formula("mom_ratio")
    assert dict(formula.expression.left.params)["window"] == 250
    assert dict(formula.expression.right.params) == {}


def test_rewrites_factor_params_in_nested_composition():
    resolve_rule, _ = overlay_resolvers(
        parse_overlay({"factor.momentum.window": 250}), _resolve_rule, _resolve_formula
    )
    rule = resolve_rule("combo")
    assert dict(rule.root.operands[1].left.params)["window"] == 250


def test_replaces_rule_threshold():
    resolve_rule, _ = overlay_resolvers(
        parse_overlay({"rule.per_rule.threshold": 8}), _resolve_rule, _resolve_formula
    )
    assert resolve_rule("per_rule").root.right.value == 8.0


def test_stored_rule_is_untouched():
    resolve_rule, _ = overlay_resolvers(
        parse_overlay({"rule.per_rule.threshold": 8}), _resolve_rule, _resolve_formula
    )
    resolve_rule("per_rule")
    assert PER_RULE.root.right.value == 15.0


def test_threshold_on_composite_rule_is_rejected():
    """AND로 묶인 룰은 '어느 상수인가'가 모호하다 — 조용히 첫 번째를 고르면 결과가 거짓이 된다."""
    with pytest.raises(OverlayError, match="단일 Predicate가 아니"):
        overlay_resolvers(
            parse_overlay({"rule.combo.threshold": 8}), _resolve_rule, _resolve_formula
        )


def test_threshold_without_constant_operand_is_rejected():
    """적용 불가는 리졸브 시점이 아니라 리졸버를 만들 때 드러나야 한다 — 그래야 조합·폴드마다
    같은 실패가 반복된 뒤 원인이 파묻히지 않는다."""
    two_factors = Rule(
        id="cross", name="cross", version="1",
        root=Predicate(FactorOperand("price", "close", {}), ">", FactorOperand("sma", "sma", {})),
    )
    with pytest.raises(OverlayError, match="상수 피연산자가 없습니다"):
        overlay_resolvers(
            parse_overlay({"rule.cross.threshold": 8}),
            lambda rid: two_factors if rid == "cross" else None,
            _resolve_formula,
        )


def test_threshold_on_missing_rule_fails_immediately():
    """오타 하나로 '스윕은 돌았는데 전부 같은 결과'가 되는 것을 막는다."""
    with pytest.raises(OverlayError, match="미존재 룰"):
        overlay_resolvers(
            parse_overlay({"rule.typo_rule.threshold": 8}), _resolve_rule, _resolve_formula
        )


def test_missing_rule_still_resolves_to_none():
    resolve_rule, resolve_formula = overlay_resolvers(
        parse_overlay({"factor.momentum.window": 250}), _resolve_rule, _resolve_formula
    )
    assert resolve_rule("nope") is None
    assert resolve_formula("nope") is None


# --- 참조 선택자(@현재값) ---


def test_selector_targets_only_matching_reference():
    """골든크로스처럼 같은 팩터를 두 번 쓰는 전략에서 단기 창만 바꿀 수 있어야 한다."""
    cross = Rule(
        id="cross", name="cross", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    resolve_rule, _ = overlay_resolvers(
        parse_overlay({"factor.sma@5.window": 3}),
        lambda rid: cross if rid == "cross" else None,
        _resolve_formula,
    )
    root = resolve_rule("cross").root
    assert dict(root.left.params)["window"] == 3
    assert dict(root.right.params)["window"] == 20


def test_without_selector_all_references_change():
    cross = Rule(
        id="cross", name="cross", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    resolve_rule, _ = overlay_resolvers(
        parse_overlay({"factor.sma.window": 3}),
        lambda rid: cross if rid == "cross" else None,
        _resolve_formula,
    )
    root = resolve_rule("cross").root
    assert dict(root.left.params)["window"] == 3
    assert dict(root.right.params)["window"] == 3


def test_selector_matches_factor_refs_too():
    defn = _defn(factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})))
    result = apply_overlay(defn, parse_overlay({"factor.sma@5.window": 3}))
    windows = sorted(dict(ref.params)["window"] for ref in result.factor_refs)
    assert windows == [3, 20]


def test_selector_with_no_match_changes_nothing():
    defn = _defn()
    result = apply_overlay(defn, parse_overlay({"factor.momentum@999.window": 3}))
    assert dict(result.factor_refs[0].params)["window"] == 60


def test_rejects_key_without_factor_id():
    with pytest.raises(OverlayError, match="factor_id가 없습니다"):
        parse_overlay({"factor.@5.window": 3})
