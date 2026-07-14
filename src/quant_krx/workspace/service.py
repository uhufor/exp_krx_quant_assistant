from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import date, datetime
from typing import Literal, TypeVar

from quant_krx._jsonnorm import ValidationResult
from quant_krx.factors import FactorInput
from quant_krx.formula.definition import BinaryOp, Formula, UnaryOp
from quant_krx.formula.definition import FormulaOperand as FormulaFormulaOperand
from quant_krx.formula.validation import validate_formula
from quant_krx.rule.definition import Composition, Predicate, Rule
from quant_krx.rule.definition import FormulaOperand as RuleFormulaOperand
from quant_krx.rule.validation import validate_rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.strategy.validation import is_runnable as strategy_is_runnable
from quant_krx.strategy.validation import validate_definition
from quant_krx.workspace.backtest import BacktestReport, run_backtest
from quant_krx.workspace.errors import WorkspaceError
from quant_krx.workspace.templates import BUILTIN_TEMPLATES, StrategyBundle, TemplateInfo

_Entity = TypeVar("_Entity", Formula, Rule, StrategyDefinition)


def _rule_formula_ids(rule: Rule) -> set[str]:
    """Rule 트리가 직접 참조하는 FormulaOperand.formula_id 집합(좌→우 순회)."""
    ids: set[str] = set()

    def walk(node: Predicate | Composition) -> None:
        if isinstance(node, Predicate):
            for operand in (node.left, node.right):
                if isinstance(operand, RuleFormulaOperand):
                    ids.add(operand.formula_id)
        elif isinstance(node, Composition):
            for child in node.operands:
                walk(child)

    walk(rule.root)
    return ids


def _formula_operand_ids(expr: BinaryOp | UnaryOp | FormulaFormulaOperand | object) -> list[str]:
    if isinstance(expr, BinaryOp):
        return _formula_operand_ids(expr.left) + _formula_operand_ids(expr.right)
    if isinstance(expr, UnaryOp):
        return _formula_operand_ids(expr.operand)
    if isinstance(expr, FormulaFormulaOperand):
        return [expr.formula_id]
    return []


def _expand_formula_closure(seed_ids: set[str], resolve_formula) -> set[str]:
    """seed_ids에서 시작해 Formula 간 참조를 전이 확장한 formula_id 집합(미존재는 스킵)."""
    seen: set[str] = set()
    stack = list(seed_ids)
    while stack:
        fid = stack.pop()
        if fid in seen:
            continue
        seen.add(fid)
        formula = resolve_formula(fid)
        if formula is None:
            continue
        for child_id in _formula_operand_ids(formula.expression):
            if child_id not in seen:
                stack.append(child_id)
    return seen


class WorkspaceService:
    """R02/R01/storage/백테스트 엔진을 조합하는 오케스트레이션 파사드(FR-01).

    로직은 이 클래스에, I/O(입력 파싱·표 출력·종료 코드)는 CLI에 둔다. CRUD는 R02 저장
    게이트로 위임하며 신규 저장 로직을 두지 않는다.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- Strategy CRUD (R02 저장 게이트 위임, 신규 로직 없음) ---

    def upsert_strategy(self, defn: StrategyDefinition, *, now: datetime) -> None:
        self._guard_active_reference("strategy", defn.id)
        self._db.upsert_strategy(defn, now=now)

    def get_strategy(self, strategy_id: str) -> StrategyDefinition | None:
        return self._db.get_strategy(strategy_id)

    def list_strategies(self) -> tuple[StrategyDefinition, ...]:
        return self._db.list_strategies()

    def delete_strategy(self, strategy_id: str) -> None:
        self._guard_active_reference("strategy", strategy_id)
        self._db.delete_strategy(strategy_id)

    # --- Rule CRUD ---

    def upsert_rule(self, rule: Rule, *, now: datetime) -> None:
        self._guard_active_reference("rule", rule.id)
        self._db.upsert_rule(rule, now=now)

    def get_rule(self, rule_id: str) -> Rule | None:
        return self._db.get_rule(rule_id)

    def list_rules(self) -> tuple[Rule, ...]:
        return self._db.list_rules()

    def delete_rule(self, rule_id: str) -> None:
        self._guard_active_reference("rule", rule_id)
        self._db.delete_rule(rule_id)

    # --- Formula CRUD ---

    def upsert_formula(self, formula: Formula, *, now: datetime) -> None:
        self._guard_active_reference("formula", formula.id)
        self._db.upsert_formula(formula, now=now)

    def get_formula(self, formula_id: str) -> Formula | None:
        return self._db.get_formula(formula_id)

    def list_formulas(self) -> tuple[Formula, ...]:
        return self._db.list_formulas()

    def delete_formula(self, formula_id: str) -> None:
        self._guard_active_reference("formula", formula_id)
        self._db.delete_formula(formula_id)

    # --- 전이 검증 (FR-02, R02 검증기 3종 조합 — 신규 검증 로직 0) ---

    def validate_strategy(self, defn: StrategyDefinition) -> ValidationResult:
        base_result = validate_definition(
            defn, resolve_rule=self.get_rule, resolve_formula=self.get_formula
        )
        errors: list[str] = list(base_result.errors)

        if defn.rule is not None:
            for rid in tuple(defn.rule.entry) + tuple(defn.rule.exit):
                rule = self.get_rule(rid)
                if rule is None:
                    continue  # validate_definition이 이미 미존재로 보고
                errors.extend(validate_rule(rule, resolve_formula=self.get_formula).errors)

            for kind, fid in self._transitive_closure(defn):
                if kind != "formula":
                    continue
                formula = self.get_formula(fid)
                if formula is None:
                    continue
                errors.extend(validate_formula(formula, resolve_formula=self.get_formula).errors)

        return ValidationResult(ok=not errors, errors=tuple(errors))

    # --- 활성 참조 보호 (FR-04a, C1-i — 온디맨드 전이 폐포, 상태 무보유) ---

    def _transitive_closure(self, defn: StrategyDefinition) -> set[tuple[str, str]]:
        """defn의 rule 슬롯이 전이 참조하는 (kind, id) 집합. rule=None(초안)이면 빈 집합."""
        closure: set[tuple[str, str]] = set()
        if defn.rule is None:
            return closure
        formula_seed: set[str] = set()
        for rid in tuple(defn.rule.entry) + tuple(defn.rule.exit):
            closure.add(("rule", rid))
            rule = self.get_rule(rid)
            if rule is not None:
                formula_seed |= _rule_formula_ids(rule)
        for fid in _expand_formula_closure(formula_seed, self.get_formula):
            closure.add(("formula", fid))
        return closure

    def _active_blockers(self, target_kind: str, target_id: str) -> tuple[str, ...]:
        """target을 참조하는 활성 전략 id 목록(정렬). 색인 테이블 없이 매 호출 재계산(drift 0)."""
        blockers: list[str] = []
        for sid in self.list_active():
            if target_kind == "strategy" and sid == target_id:
                blockers.append(sid)
                continue
            defn = self.get_strategy(sid)
            if defn is not None and (target_kind, target_id) in self._transitive_closure(defn):
                blockers.append(sid)
        return tuple(sorted(blockers))

    def _guard_active_reference(self, target_kind: str, target_id: str) -> None:
        blockers = self._active_blockers(target_kind, target_id)
        if blockers:
            raise WorkspaceError(
                f"활성 전략 {list(blockers)}가 참조 중입니다. 먼저 비활성화하십시오."
            )

    # --- 활성화 (FR-03/04, strategy_activation) ---

    def _require_runnable_and_valid(self, strategy_id: str) -> StrategyDefinition:
        defn = self.get_strategy(strategy_id)
        if defn is None:
            raise WorkspaceError(f"전략 '{strategy_id}'을(를) 찾을 수 없습니다")
        if not strategy_is_runnable(defn):
            raise WorkspaceError(
                f"전략 '{strategy_id}'은(는) 실행 가능(runnable) 상태가 아닙니다"
                "(rule 슬롯이 roles 형상이고 entry가 1개 이상이어야 합니다)"
            )
        result = self.validate_strategy(defn)
        if not result.ok:
            raise WorkspaceError(f"전략 '{strategy_id}' 검증 실패: " + "; ".join(result.errors))
        return defn

    def is_runnable(self, strategy_id: str) -> bool:
        defn = self.get_strategy(strategy_id)
        return defn is not None and strategy_is_runnable(defn)

    def activate(self, strategy_id: str, *, now: datetime) -> None:
        self._require_runnable_and_valid(strategy_id)
        self._db.upsert_activation(strategy_id, active=True, now=now)

    def deactivate(self, strategy_id: str, *, now: datetime) -> None:
        self._db.upsert_activation(strategy_id, active=False, now=now)

    def is_active(self, strategy_id: str) -> bool:
        return self._db.get_activation(strategy_id)

    def list_active(self) -> tuple[str, ...]:
        return self._db.list_active_strategy_ids()

    # --- 백테스트 (FR-13) ---

    def backtest(
        self,
        strategy_id: str,
        *,
        data: dict[str, FactorInput],
        start: date | None = None,
        end: date | None = None,
        fees: float,
        slippage: float,
        benchmark: object | None = None,
    ) -> BacktestReport:
        defn = self._require_runnable_and_valid(strategy_id)
        return run_backtest(
            defn, data,
            fees=fees, slippage=slippage, benchmark=benchmark,
            resolve_formula=self.get_formula, resolve_rule=self.get_rule,
            start=start, end=end,
        )

    # --- Template (FR-19/20/21) ---

    def _collect_bundle(self, defn: StrategyDefinition) -> StrategyBundle:
        """defn + 전이 참조 Rule/Formula 폐포를 StrategyBundle로 수집(Export/Template 공용)."""
        closure = sorted(self._transitive_closure(defn))
        rules = tuple(
            rule
            for kind, rid in closure
            if kind == "rule" and (rule := self.get_rule(rid)) is not None
        )
        formulas = tuple(
            formula
            for kind, fid in closure
            if kind == "formula" and (formula := self.get_formula(fid)) is not None
        )
        return StrategyBundle(strategy=defn, rules=rules, formulas=formulas)

    def create_from_template(
        self, template_id: str, new_id: str, *, now: datetime
    ) -> StrategyDefinition:
        bundle = self.get_template(template_id)
        if bundle is None:
            raise WorkspaceError(f"템플릿 '{template_id}'을(를) 찾을 수 없습니다")
        for formula in bundle.formulas:
            if self.get_formula(formula.id) is None:
                self.upsert_formula(formula, now=now)
        for rule in bundle.rules:
            if self.get_rule(rule.id) is None:
                self.upsert_rule(rule, now=now)
        new_defn = dataclasses.replace(bundle.strategy, id=new_id)
        self.upsert_strategy(new_defn, now=now)
        return new_defn

    def save_as_template(self, strategy_id: str, template_id: str, *, now: datetime) -> None:
        if template_id in BUILTIN_TEMPLATES:
            raise WorkspaceError(f"template_id '{template_id}'은(는) Built-in과 충돌합니다")
        defn = self.get_strategy(strategy_id)
        if defn is None:
            raise WorkspaceError(f"전략 '{strategy_id}'을(를) 찾을 수 없습니다")
        bundle = self._collect_bundle(defn)
        self._db.upsert_template(template_id, name=defn.name, bundle=bundle.to_dict(), now=now)

    def list_templates(self) -> tuple[TemplateInfo, ...]:
        builtin = [
            TemplateInfo(template_id=tid, origin="builtin", name=b.strategy.name)
            for tid, b in BUILTIN_TEMPLATES.items()
        ]
        user = [
            TemplateInfo(template_id=tid, origin="user", name=name)
            for tid, name in self._db.list_templates()
        ]
        return tuple(sorted(builtin + user, key=lambda t: t.template_id))

    def get_template(self, template_id: str) -> StrategyBundle | None:
        if template_id in BUILTIN_TEMPLATES:
            return BUILTIN_TEMPLATES[template_id]
        raw = self._db.get_template(template_id)
        return StrategyBundle.from_dict(raw) if raw is not None else None

    def delete_template(self, template_id: str) -> None:
        if template_id in BUILTIN_TEMPLATES:
            raise WorkspaceError(f"Built-in Template '{template_id}'은(는) 삭제할 수 없습니다")
        self._db.delete_template(template_id)

    # --- Import/Export (FR-22/23) ---

    def export_strategy(self, strategy_id: str) -> StrategyBundle:
        defn = self.get_strategy(strategy_id)
        if defn is None:
            raise WorkspaceError(f"전략 '{strategy_id}'을(를) 찾을 수 없습니다")
        return self._collect_bundle(defn)

    def _import_one(
        self,
        entity: _Entity,
        *,
        get_fn: Callable[[str], _Entity | None],
        upsert_fn: Callable[..., None],
        now: datetime,
        on_conflict: Literal["reject", "overwrite"],
        kind_label: str,
    ) -> None:
        existing = get_fn(entity.id)
        if existing is None:
            upsert_fn(entity, now=now)
            return
        if existing == entity:
            return  # 동일 canonical — 멱등 통과(재저장 없음)
        if on_conflict == "overwrite":
            upsert_fn(entity, now=now)  # upsert_fn이 FR-04a 활성 참조 보호를 이미 강제
            return
        raise WorkspaceError(
            f"{kind_label} id '{entity.id}' 충돌 — 기존 정의와 내용이 다릅니다"
            "(--overwrite 지정 시 대체 가능)"
        )

    def import_strategy(
        self,
        bundle: StrategyBundle,
        *,
        now: datetime,
        on_conflict: Literal["reject", "overwrite"] = "reject",
    ) -> None:
        """Formula → Rule → Strategy 의존 위상 순서로 검증·저장(FR-23)."""
        for formula in bundle.formulas:
            self._import_one(
                formula, get_fn=self.get_formula, upsert_fn=self.upsert_formula,
                now=now, on_conflict=on_conflict, kind_label="formula",
            )
        for rule in bundle.rules:
            self._import_one(
                rule, get_fn=self.get_rule, upsert_fn=self.upsert_rule,
                now=now, on_conflict=on_conflict, kind_label="rule",
            )
        self._import_one(
            bundle.strategy, get_fn=self.get_strategy, upsert_fn=self.upsert_strategy,
            now=now, on_conflict=on_conflict, kind_label="strategy",
        )
