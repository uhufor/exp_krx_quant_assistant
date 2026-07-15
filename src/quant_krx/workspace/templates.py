from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from quant_krx.formula.definition import Formula
from quant_krx.rule.definition import ConstantOperand, FactorOperand, Predicate, Rule
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe

if TYPE_CHECKING:
    from quant_krx.workspace.service import WorkspaceService


@dataclass(frozen=True)
class StrategyBundle:
    """Export/Import·Template 공통 번들 형상(전이 참조 폐포 포함)."""

    strategy: StrategyDefinition
    rules: tuple[Rule, ...] = ()
    formulas: tuple[Formula, ...] = ()
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.to_dict(),
            "rules": [r.to_dict() for r in self.rules],
            "formulas": [f.to_dict() for f in self.formulas],
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StrategyBundle:
        return cls(
            strategy=StrategyDefinition.from_dict(d["strategy"]),
            rules=tuple(Rule.from_dict(r) for r in d.get("rules", [])),
            formulas=tuple(Formula.from_dict(f) for f in d.get("formulas", [])),
            schema_version=d.get("schema_version", 1),
        )


@dataclass(frozen=True)
class TemplateInfo:
    template_id: str
    origin: Literal["builtin", "user"]
    name: str


def _ma_crossover_bundle() -> StrategyBundle:
    short = FactorOperand("sma", "sma", {"window": 20})
    long_ = FactorOperand("sma", "sma", {"window": 60})
    entry_rule = Rule(
        id="ma_crossover_entry", name="MA 골든크로스 진입", version="1",
        root=Predicate(short, "crosses_above", long_),
    )
    exit_rule = Rule(
        id="ma_crossover_exit", name="MA 데드크로스 청산", version="1",
        root=Predicate(short, "crosses_below", long_),
    )
    strategy = StrategyDefinition(
        id="ma_crossover", name="이동평균 골든크로스", version="1",
        factor_refs=(FactorRef("sma", {"window": 20}), FactorRef("sma", {"window": 60})),
        universe=Universe(),
        rule=RuleBinding(entry=("ma_crossover_entry",), exit=("ma_crossover_exit",)),
    )
    return StrategyBundle(strategy=strategy, rules=(entry_rule, exit_rule))


def _rsi_breakout_bundle() -> StrategyBundle:
    rsi = FactorOperand("rsi", "rsi", {"window": 14})
    entry_rule = Rule(
        id="rsi_breakout_entry", name="RSI 과매도 진입", version="1",
        root=Predicate(rsi, "<", ConstantOperand(30)),
    )
    exit_rule = Rule(
        id="rsi_breakout_exit", name="RSI 과매수 청산", version="1",
        root=Predicate(rsi, ">", ConstantOperand(70)),
    )
    strategy = StrategyDefinition(
        id="rsi_breakout", name="RSI 과매도 반등", version="1",
        factor_refs=(FactorRef("rsi", {"window": 14}),),
        universe=Universe(),
        rule=RuleBinding(entry=("rsi_breakout_entry",), exit=("rsi_breakout_exit",)),
    )
    return StrategyBundle(strategy=strategy, rules=(entry_rule, exit_rule))


def _bollinger_band_bundle() -> StrategyBundle:
    bb_params = {"window": 20, "num_std": 2.0}
    close = FactorOperand("price", "close")
    lower = FactorOperand("bollinger", "lower", bb_params)
    middle = FactorOperand("bollinger", "middle", bb_params)
    entry_rule = Rule(
        id="bollinger_band_entry", name="볼린저 하단 이탈 진입", version="1",
        root=Predicate(close, "crosses_below", lower),
    )
    exit_rule = Rule(
        id="bollinger_band_exit", name="볼린저 중심선 회귀 청산", version="1",
        root=Predicate(close, "crosses_above", middle),
    )
    strategy = StrategyDefinition(
        id="bollinger_band", name="볼린저 밴드 평균회귀", version="1",
        factor_refs=(FactorRef("price"), FactorRef("bollinger", bb_params)),
        universe=Universe(),
        rule=RuleBinding(entry=("bollinger_band_entry",), exit=("bollinger_band_exit",)),
    )
    return StrategyBundle(strategy=strategy, rules=(entry_rule, exit_rule))


def _macd_bundle() -> StrategyBundle:
    macd_params = {"fast": 12, "slow": 26, "signal": 9}
    macd_line = FactorOperand("macd", "macd", macd_params)
    signal_line = FactorOperand("macd", "signal", macd_params)
    entry_rule = Rule(
        id="macd_entry", name="MACD 크로스 진입", version="1",
        root=Predicate(macd_line, "crosses_above", signal_line),
    )
    exit_rule = Rule(
        id="macd_exit", name="MACD 데드크로스 청산", version="1",
        root=Predicate(macd_line, "crosses_below", signal_line),
    )
    strategy = StrategyDefinition(
        id="macd", name="MACD 크로스", version="1",
        factor_refs=(FactorRef("macd", macd_params),),
        universe=Universe(),
        rule=RuleBinding(entry=("macd_entry",), exit=("macd_exit",)),
    )
    return StrategyBundle(strategy=strategy, rules=(entry_rule, exit_rule))


def _momentum_bundle() -> StrategyBundle:
    mom_params = {"lookback": 252, "skip": 21}
    momentum = FactorOperand("momentum", "momentum", mom_params)
    entry_rule = Rule(
        id="momentum_entry", name="절대 모멘텀 진입", version="1",
        root=Predicate(momentum, ">", ConstantOperand(0)),
    )
    exit_rule = Rule(
        id="momentum_exit", name="절대 모멘텀 청산", version="1",
        root=Predicate(momentum, "<", ConstantOperand(0)),
    )
    strategy = StrategyDefinition(
        id="momentum", name="절대 모멘텀", version="1",
        factor_refs=(FactorRef("momentum", mom_params),),
        universe=Universe(),
        rule=RuleBinding(entry=("momentum_entry",), exit=("momentum_exit",)),
    )
    return StrategyBundle(strategy=strategy, rules=(entry_rule, exit_rule))


BUILTIN_TEMPLATES: dict[str, StrategyBundle] = {
    "ma_crossover": _ma_crossover_bundle(),
    "rsi_breakout": _rsi_breakout_bundle(),
    "bollinger_band": _bollinger_band_bundle(),
    "macd": _macd_bundle(),
    "momentum": _momentum_bundle(),
}


def seed_builtin_strategies(svc: WorkspaceService, now: datetime) -> None:
    """Daily 부트스트랩 인라인 멱등 시드(FR-14a, C2-i).

    각 Built-in 전략 id가 이미 존재하면 정의·활성 상태를 일절 변경하지 않는다
    (사용자의 비활성화·수정 결정을 재실행이 덮어쓰지 않음).
    """
    for bundle in BUILTIN_TEMPLATES.values():
        if svc.get_strategy(bundle.strategy.id) is not None:
            continue
        for formula in bundle.formulas:
            svc.upsert_formula(formula, now=now)
        for rule in bundle.rules:
            svc.upsert_rule(rule, now=now)
        svc.upsert_strategy(bundle.strategy, now=now)
        svc.activate(bundle.strategy.id, now=now)
