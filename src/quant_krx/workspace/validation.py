"""OOS / 워크포워드 검증(P4).

전 구간 백테스트 성과 하나만으로는 "그 숫자가 미래에도 재현될지"를 알 수 없다. 파라미터를
손으로 몇 번 바꿔 좋은 값을 고르는 순간 전 구간이 사실상 인샘플이 되지만 기존 리포트는 그
사실을 표시하지 않는다. 여기서는 폴드마다

1. **학습(IS) 구간에서만** 그리드 전체를 돌려 목적함수 최댓값 파라미터를 고르고,
2. **검증(OOS) 구간에서 그 파라미터로만** 성과를 재고

두 성과의 낙차·선택 파라미터의 흔들림·OOS 일관성을 과최적화 신호로 제시한다.

비용 구조상 중요한 점: 데이터(`FactorInput`)는 전 구간을 한 번만 조립해 넘기고 폴드는
`start`/`end`로만 자른다. 팩터는 전 구간에서 계산된 뒤 슬라이스된 인덱스로 정렬되므로
(`evaluation.py::_eval_factor_operand` -> `numeric.align`) **폴드를 잘라도 워밍업 손실이 없다.**
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from quant_krx.factors import FactorInput
from quant_krx.quant.base import BacktestMetrics
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.workspace.backtest import PORTFOLIO_KEY, UniverseResolver, run_backtest
from quant_krx.workspace.errors import WorkspaceError
from quant_krx.workspace.evaluation import FormulaResolver, RuleResolver
from quant_krx.workspace.overlay import (
    OverlayError,
    apply_overlay,
    expand_grid,
    overlay_resolvers,
    parse_overlay,
)
from quant_krx.workspace.walkforward import Fold, build_folds

# 목적함수 — 학습 구간에서 무엇을 최대화해 파라미터를 고를 것인가.
# 총수익률 단독은 MDD를 무시해 과최적화를 오히려 부추기므로 기본값은 Sharpe다.
OBJECTIVES = ("sharpe", "total_return", "calmar")

# 진행 콜백: (fold_index, n_folds, stage, done, total)
ProgressCallback = Callable[[int, int, str, int, int], None]


class ValidationError(WorkspaceError):
    """검증 설정 오류 또는 모든 폴드 실패."""


@dataclass(frozen=True)
class ValidationSpec:
    """검증 실행 설정. 저장하지 않는 단발 스펙이다(엔티티로 승격하지 않음)."""

    mode: str = "walkforward"
    n_folds: int = 3
    test_ratio: float = 0.3
    anchored: bool = True
    objective: str = "sharpe"
    grid: Mapping[str, list[Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.objective not in OBJECTIVES:
            raise ValidationError(
                f"미지의 objective '{self.objective}'(허용: {list(OBJECTIVES)})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "n_folds": self.n_folds,
            "test_ratio": self.test_ratio,
            "anchored": self.anchored,
            "objective": self.objective,
            "grid": {k: list(v) for k, v in self.grid.items()},
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ValidationSpec:
        unknown = set(d) - {"mode", "n_folds", "test_ratio", "anchored", "objective", "grid"}
        if unknown:
            raise ValidationError(f"미지의 스펙 필드: {sorted(unknown)}")
        return cls(
            mode=d.get("mode", "walkforward"),
            n_folds=int(d.get("n_folds", 3)),
            test_ratio=float(d.get("test_ratio", 0.3)),
            anchored=bool(d.get("anchored", True)),
            objective=d.get("objective", "sharpe"),
            grid=dict(d.get("grid", {})),
        )


@dataclass(frozen=True)
class Candidate:
    """학습 구간에서 평가된 그리드 조합 1건(선택 근거를 남기기 위해 전부 보존)."""

    params: Mapping[str, Any]
    objective: float
    total_return: float
    mdd: float
    trade_count: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": dict(self.params),
            "objective": _json_float(self.objective),
            "total_return": _json_float(self.total_return),
            "mdd": _json_float(self.mdd),
            "trade_count": self.trade_count,
            "error": self.error,
        }


@dataclass(frozen=True)
class FoldResult:
    fold: Fold
    params: Mapping[str, Any] = field(default_factory=dict)
    train_metrics: BacktestMetrics | None = None
    test_metrics: BacktestMetrics | None = None
    test_equity: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    candidates: tuple[Candidate, ...] = ()
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.test_metrics is not None


@dataclass(frozen=True)
class ValidationSummary:
    """과최적화 판단 지표. 값 자체보다 **IS와 OOS의 낙차**가 핵심이다."""

    is_objective: float = float("nan")   # 폴드별 학습 목적함수 평균
    oos_objective: float = float("nan")  # 폴드별 검증 목적함수 평균
    degradation: float = float("nan")    # 1 - OOS/IS (IS가 양수일 때만 의미)
    param_stability: float = float("nan")  # 최빈 파라미터 조합 비율(그리드 없으면 1.0)
    oos_consistency: float = float("nan")  # 검증 수익 폴드 비율
    oos_total_return: float = float("nan")  # 폴드 검증 구간을 이어붙인 합성 성과
    oos_mdd: float = float("nan")
    folds_ok: int = 0
    folds_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_objective": _json_float(self.is_objective),
            "oos_objective": _json_float(self.oos_objective),
            "degradation": _json_float(self.degradation),
            "param_stability": _json_float(self.param_stability),
            "oos_consistency": _json_float(self.oos_consistency),
            "oos_total_return": _json_float(self.oos_total_return),
            "oos_mdd": _json_float(self.oos_mdd),
            "folds_ok": self.folds_ok,
            "folds_total": self.folds_total,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ValidationSummary:
        def _f(key: str) -> float:
            value = d.get(key)
            return float("nan") if value is None else float(value)

        return cls(
            is_objective=_f("is_objective"),
            oos_objective=_f("oos_objective"),
            degradation=_f("degradation"),
            param_stability=_f("param_stability"),
            oos_consistency=_f("oos_consistency"),
            oos_total_return=_f("oos_total_return"),
            oos_mdd=_f("oos_mdd"),
            folds_ok=int(d.get("folds_ok", 0)),
            folds_total=int(d.get("folds_total", 0)),
        )


@dataclass(frozen=True)
class ValidationReport:
    validation_id: str
    strategy_id: str
    spec: ValidationSpec
    folds: tuple[FoldResult, ...]
    summary: ValidationSummary
    oos_equity: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    executed_at: datetime | None = None


def _json_float(value: float | None) -> float | None:
    """NaN/inf는 JSON 표준이 아니므로 None으로 낮춘다(직렬화 계약은 serialization.py와 동일)."""
    if value is None:
        return None
    value = float(value)
    return None if not math.isfinite(value) else value


def objective_value(metrics: BacktestMetrics, objective: str) -> float:
    """목적함수 값. 계산 불가(NaN)는 그대로 NaN을 돌려주고 선택 단계에서 탈락시킨다."""
    if objective == "sharpe":
        return float(metrics.sharpe)
    if objective == "total_return":
        return float(metrics.total_return)
    if objective == "calmar":
        mdd = abs(float(metrics.mdd))
        if mdd == 0.0:
            # 낙폭이 없으면 비율이 발산한다 — 무한대가 승자가 되면 "거래를 거의 안 한
            # 파라미터"가 항상 뽑히므로 선택 불가로 처리한다.
            return float("nan")
        return float(metrics.total_return) / mdd
    raise ValidationError(f"미지의 objective '{objective}'")


def _representative_equity(report) -> pd.Series:
    """리포트에서 대표 자산곡선 1개 — 포트폴리오 모드는 계좌 곡선, 아니면 첫 종목."""
    if PORTFOLIO_KEY in report.results:
        return report.results[PORTFOLIO_KEY].equity_curve
    if not report.results:
        return pd.Series(dtype=float)
    return next(iter(report.results.values())).equity_curve


def _mean(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    return sum(finite) / len(finite) if finite else float("nan")


def _chain_oos_equity(fold_results: tuple[FoldResult, ...]) -> pd.Series:
    """폴드별 검증 구간 곡선을 1로 정규화해 이어붙인 합성 곡선.

    각 폴드가 자기 자본에서 다시 시작하므로 그냥 붙이면 계단이 생긴다. 폴드 내부 수익률만
    가져와 곱으로 이어야 "이 전략을 계속 굴렸다면 겪었을 성과"가 된다.
    """
    pieces: list[pd.Series] = []
    level = 1.0
    for result in fold_results:
        curve = result.test_equity
        if not result.ok or curve.empty or float(curve.iloc[0]) == 0.0:
            continue
        normalized = curve.astype(float) / float(curve.iloc[0]) * level
        pieces.append(normalized)
        level = float(normalized.iloc[-1])
    if not pieces:
        return pd.Series(dtype=float)
    combined = pd.concat(pieces)
    return combined[~combined.index.duplicated(keep="last")].sort_index()


def _curve_stats(curve: pd.Series) -> tuple[float, float]:
    """(총수익률, MDD) — 합성 곡선은 vectorbt를 거치지 않으므로 여기서 직접 계산한다."""
    if curve.empty:
        return float("nan"), float("nan")
    total_return = float(curve.iloc[-1]) / float(curve.iloc[0]) - 1.0
    running_max = curve.cummax()
    drawdown = curve / running_max - 1.0
    return total_return, float(-drawdown.min())


def _param_stability(fold_results: tuple[FoldResult, ...], has_grid: bool) -> float:
    """폴드마다 다른 파라미터가 뽑히면 = 노이즈에 적합했다는 신호."""
    if not has_grid:
        return 1.0  # 고를 것이 없으면 흔들릴 것도 없다
    chosen = [tuple(sorted(r.params.items())) for r in fold_results if r.ok]
    if not chosen:
        return float("nan")
    top = max(chosen.count(c) for c in set(chosen))
    return top / len(chosen)


def build_summary(
    fold_results: tuple[FoldResult, ...], *, objective: str, has_grid: bool
) -> tuple[ValidationSummary, pd.Series]:
    ok_folds = tuple(r for r in fold_results if r.ok)
    is_values = [objective_value(r.train_metrics, objective) for r in ok_folds if r.train_metrics]
    oos_values = [objective_value(r.test_metrics, objective) for r in ok_folds if r.test_metrics]

    is_mean = _mean(is_values)
    oos_mean = _mean(oos_values)
    # IS가 0 이하면 "저하율"이 부호가 뒤집혀 엉뚱한 값이 된다(예: IS=-1, OOS=-2 -> -1.0).
    # 애초에 학습 구간에서도 실패한 전략이므로 저하율을 계산하지 않는다.
    degradation = (
        1.0 - oos_mean / is_mean
        if math.isfinite(is_mean) and math.isfinite(oos_mean) and is_mean > 0
        else float("nan")
    )

    oos_curve = _chain_oos_equity(fold_results)
    oos_total_return, oos_mdd = _curve_stats(oos_curve)

    positive = [
        1.0 for r in ok_folds if r.test_metrics and float(r.test_metrics.total_return) > 0
    ]
    consistency = len(positive) / len(ok_folds) if ok_folds else float("nan")

    return (
        ValidationSummary(
            is_objective=is_mean,
            oos_objective=oos_mean,
            degradation=degradation,
            param_stability=_param_stability(fold_results, has_grid),
            oos_consistency=consistency,
            oos_total_return=oos_total_return,
            oos_mdd=oos_mdd,
            folds_ok=len(ok_folds),
            folds_total=len(fold_results),
        ),
        oos_curve,
    )


def _no_candidate_reason(candidates: list[Candidate]) -> str:
    """폴드에서 아무 조합도 뽑히지 않은 이유를 진단 가능한 문장으로 만든다.

    "목적함수가 모두 NaN"만 돌려주면 원인을 알 수 없다. 가장 흔한 원인은 **거래가 한 건도
    발생하지 않은 것**이고, 그 중에서도 같은 팩터를 여러 번 쓰는 전략(골든크로스 등)에서
    선택자 없이 스윕해 두 참조가 같은 값이 되어버린 경우가 많다 — 그 경우를 짚어 준다.
    """
    errors = [c.error for c in candidates if c.error]
    if errors and len(errors) == len(candidates):
        return f"학습 구간에서 유효한 파라미터를 찾지 못했습니다({'; '.join(errors)})"
    ran = [c for c in candidates if not c.error]
    if ran and all(c.trade_count == 0 for c in ran):
        return (
            "학습 구간에서 어느 조합도 거래를 발생시키지 못했습니다"
            " — 같은 팩터를 여러 번 쓰는 전략이라면 'factor.<팩터id>@<현재값>.<파라미터>'"
            " 선택자가 필요할 수 있습니다(선택자 없이 스윕하면 두 참조가 같은 값이 되어"
            " 신호가 발생하지 않습니다)"
        )
    detail = "; ".join(errors) or "목적함수를 계산할 수 없습니다"
    return f"학습 구간에서 유효한 파라미터를 찾지 못했습니다({detail})"


def _run_window(
    defn: StrategyDefinition,
    data: dict[str, FactorInput],
    *,
    params: Mapping[str, Any],
    start: date,
    end: date,
    fees: float,
    slippage: float,
    benchmark: pd.DataFrame | None,
    resolve_formula: FormulaResolver,
    resolve_rule: RuleResolver,
    resolve_universe: UniverseResolver | None,
):
    overlay = parse_overlay(params)
    overlaid = apply_overlay(defn, overlay)
    rule_resolver, formula_resolver = overlay_resolvers(overlay, resolve_rule, resolve_formula)
    return run_backtest(
        overlaid, data,
        fees=fees, slippage=slippage, benchmark=benchmark,
        resolve_formula=formula_resolver, resolve_rule=rule_resolver,
        start=start, end=end, resolve_universe=resolve_universe,
    )


def run_validation(
    defn: StrategyDefinition,
    data: dict[str, FactorInput],
    *,
    spec: ValidationSpec,
    start: date,
    end: date,
    fees: float,
    slippage: float,
    benchmark: pd.DataFrame | None = None,
    resolve_formula: FormulaResolver,
    resolve_rule: RuleResolver,
    resolve_universe: UniverseResolver | None = None,
    on_progress: ProgressCallback | None = None,
    now: datetime | None = None,
) -> ValidationReport:
    """폴드별 (학습 구간 파라미터 선택 -> 검증 구간 성과 측정)을 수행한다.

    폴드 단위 실패는 격리한다(FR-17과 같은 원칙) — 특정 구간에 데이터가 없어도 나머지
    폴드 결과는 그대로 살리고 사유만 남긴다. 다만 **전 폴드가 실패하면** 요약이 전부
    NaN인 빈 리포트를 돌려주는 대신 예외로 알린다.
    """
    executed_at = now or datetime.now()
    folds = build_folds(
        start, end,
        mode=spec.mode, n_folds=spec.n_folds,
        test_ratio=spec.test_ratio, anchored=spec.anchored,
    )
    combos = expand_grid(spec.grid)
    has_grid = bool(spec.grid)

    # 주소 오타는 폴드를 다 돌린 뒤가 아니라 지금 드러나야 한다 — 조합마다 같은 실패가
    # 반복되면 "모든 폴드 실패" 뒤에 원인이 파묻힌다. 값 자체의 유효성(예: max_positions=0)은
    # 여기서 보지 않는다(조합 단위로 격리되는 정상적인 실패이므로).
    for combo in combos:
        try:
            overlay_resolvers(parse_overlay(combo), resolve_rule, resolve_formula)
        except OverlayError as e:
            raise ValidationError(f"파라미터 그리드 오류: {e}") from e

    fold_results: list[FoldResult] = []
    for fold in folds:
        candidates: list[Candidate] = []
        best: tuple[float, dict[str, Any], BacktestMetrics] | None = None

        for i, combo in enumerate(combos):
            if on_progress is not None:
                on_progress(fold.index, len(folds), "train", i + 1, len(combos))
            try:
                report = _run_window(
                    defn, data, params=combo,
                    start=fold.train_start, end=fold.train_end,
                    fees=fees, slippage=slippage, benchmark=benchmark,
                    resolve_formula=resolve_formula, resolve_rule=resolve_rule,
                    resolve_universe=resolve_universe,
                )
            except Exception as e:  # noqa: BLE001 — 조합 단위 격리, 사유는 candidates에 보존
                candidates.append(
                    Candidate(params=combo, objective=float("nan"),
                              total_return=float("nan"), mdd=float("nan"), error=str(e))
                )
                continue

            value = objective_value(report.metrics, spec.objective)
            candidates.append(
                Candidate(
                    params=combo, objective=value,
                    total_return=float(report.metrics.total_return),
                    mdd=float(report.metrics.mdd),
                    trade_count=int(report.metrics.trade_count),
                )
            )
            # 동점은 먼저 나온 조합이 이긴다(expand_grid가 정렬된 곱집합이라 결정적).
            if math.isfinite(value) and (best is None or value > best[0]):
                best = (value, dict(combo), report.metrics)

        if best is None:
            fold_results.append(
                FoldResult(fold=fold, candidates=tuple(candidates),
                           error=_no_candidate_reason(candidates))
            )
            continue

        if on_progress is not None:
            on_progress(fold.index, len(folds), "test", 1, 1)
        try:
            test_report = _run_window(
                defn, data, params=best[1],
                start=fold.test_start, end=fold.test_end,
                fees=fees, slippage=slippage, benchmark=benchmark,
                resolve_formula=resolve_formula, resolve_rule=resolve_rule,
                resolve_universe=resolve_universe,
            )
        except Exception as e:  # noqa: BLE001 — 폴드 단위 격리
            fold_results.append(
                FoldResult(fold=fold, params=best[1], train_metrics=best[2],
                           candidates=tuple(candidates), error=f"검증 구간 실행 실패: {e}")
            )
            continue

        fold_results.append(
            FoldResult(
                fold=fold, params=best[1],
                train_metrics=best[2], test_metrics=test_report.metrics,
                test_equity=_representative_equity(test_report),
                candidates=tuple(candidates),
            )
        )

    results = tuple(fold_results)
    if not any(r.ok for r in results):
        # 폴드마다 같은 사유가 반복되는 것이 보통이라(설정 문제는 구간과 무관) 중복을 접는다 —
        # 그러지 않으면 진단 문장이 폴드 수만큼 늘어나 정작 읽히지 않는다.
        reasons = {r.error for r in results}
        detail = (
            results[0].error
            if len(reasons) == 1
            else "; ".join(f"폴드{r.fold.index + 1}: {r.error}" for r in results)
        )
        raise ValidationError(f"모든 폴드의 검증이 실패했습니다 — {detail}")

    summary, oos_curve = build_summary(results, objective=spec.objective, has_grid=has_grid)
    return ValidationReport(
        validation_id=f"{executed_at:%Y%m%d}-{uuid.uuid4().hex[:8]}",
        strategy_id=defn.id,
        spec=spec,
        folds=results,
        summary=summary,
        oos_equity=oos_curve,
        executed_at=executed_at,
    )
