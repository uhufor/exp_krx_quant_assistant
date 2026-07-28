from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from quant_krx.factors import FactorInput
from quant_krx.quant.base import BacktestMetrics
from quant_krx.rule.definition import ConstantOperand, FactorOperand, Predicate, Rule
from quant_krx.strategy.definition import (
    FactorRef,
    PortfolioPolicy,
    RuleBinding,
    StrategyDefinition,
    Universe,
)
from quant_krx.workspace.validation import (
    Candidate,
    FoldResult,
    ValidationError,
    ValidationSpec,
    build_summary,
    objective_value,
    run_validation,
)
from quant_krx.workspace.walkforward import Fold

START = date(2022, 1, 1)
END = date(2023, 12, 31)
DAYS = (END - START).days + 1


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range(START, periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes, "high": closes, "low": closes,
            "close": closes, "volume": [10_000.0] * len(closes),
        },
        index=index,
    )


def _data(closes: list[float] | None = None) -> dict[str, FactorInput]:
    closes = closes or [100.0 + i * 0.1 for i in range(DAYS)]
    return {"005930": FactorInput(ohlcv=_ohlcv(closes), valuation=None, financials=None)}


# 임계값 스윕이 실제로 다른 결과를 내도록 close를 상수와 비교하는 진입 룰을 쓴다.
PRICE_RULE = Rule(
    id="price_rule", name="price", version="1",
    root=Predicate(FactorOperand("price", "close", {}), ">", ConstantOperand(100.0)),
)


def _resolve_rule(rule_id: str):
    return PRICE_RULE if rule_id == "price_rule" else None


def _resolve_formula(_: str):
    return None


DEFN = StrategyDefinition(
    id="v1", name="v1", version="1",
    factor_refs=(FactorRef("price"),),
    universe=Universe(symbols=("005930",)),
    rule=RuleBinding(entry=("price_rule",)),
)


def _run(spec: ValidationSpec, data=None, defn=DEFN):
    return run_validation(
        defn, data or _data(),
        spec=spec, start=START, end=END, fees=0.0, slippage=0.0,
        resolve_formula=_resolve_formula, resolve_rule=_resolve_rule,
    )


def _metrics(**kwargs) -> BacktestMetrics:
    base = dict(
        total_return=0.1, benchmark_return=float("nan"), excess_return=float("nan"),
        mdd=0.05, sharpe=1.0, sortino=1.0, trade_count=3, fees_paid=0.0,
        slippage_cost=0.0, recent_6m_return=0.0, recent_12m_return=0.0, win_rate=0.5,
    )
    base.update(kwargs)
    return BacktestMetrics(**base)


# --- 기본 실행 ---


def test_holdout_produces_one_fold_with_both_metrics():
    report = _run(ValidationSpec(mode="holdout"))

    assert len(report.folds) == 1
    fold = report.folds[0]
    assert fold.ok
    assert fold.train_metrics is not None and fold.test_metrics is not None
    assert report.summary.folds_ok == 1


def test_walkforward_produces_requested_fold_count():
    report = _run(ValidationSpec(n_folds=3, test_ratio=0.45))
    assert len(report.folds) == 3
    assert report.summary.folds_total == 3


def test_validation_id_and_strategy_id_are_set():
    report = _run(ValidationSpec(mode="holdout"))
    assert report.strategy_id == "v1"
    assert len(report.validation_id.split("-")) == 2


# --- 파라미터 선택 ---


def test_selected_params_come_from_the_grid():
    spec = ValidationSpec(mode="holdout", grid={"rule.price_rule.threshold": [50.0, 150.0]})
    report = _run(spec)

    fold = report.folds[0]
    assert set(fold.params) == {"rule.price_rule.threshold"}
    assert fold.params["rule.price_rule.threshold"] in (50.0, 150.0)
    assert len(fold.candidates) == 2


def test_selection_maximizes_the_objective_on_train_only():
    """선택은 학습 구간 성과로만 이뤄져야 한다 — 검증 구간을 보고 고르면 OOS가 아니다."""
    spec = ValidationSpec(
        mode="holdout", objective="total_return",
        grid={"rule.price_rule.threshold": [50.0, 150.0]},
    )
    report = _run(spec)

    fold = report.folds[0]
    best = max(
        (c for c in fold.candidates if math.isfinite(c.objective)), key=lambda c: c.objective
    )
    assert fold.params == dict(best.params)
    assert fold.train_metrics.total_return == pytest.approx(best.total_return)


def test_no_grid_means_empty_params_and_full_stability():
    report = _run(ValidationSpec(mode="holdout"))
    assert report.folds[0].params == {}
    assert report.summary.param_stability == 1.0


def test_candidates_preserve_every_combination_for_inspection():
    spec = ValidationSpec(
        mode="holdout",
        grid={"rule.price_rule.threshold": [50.0, 150.0, 250.0]},
    )
    report = _run(spec)
    assert len(report.folds[0].candidates) == 3


# --- 요약 지표 ---


def test_degradation_is_one_minus_oos_over_is():
    folds = (
        FoldResult(
            fold=Fold(0, START, START, START, END),
            train_metrics=_metrics(sharpe=2.0), test_metrics=_metrics(sharpe=1.0),
            test_equity=pd.Series([1.0, 1.1], index=pd.date_range("2023-01-01", periods=2)),
        ),
    )
    summary, _ = build_summary(folds, objective="sharpe", has_grid=False)
    assert summary.degradation == pytest.approx(0.5)


def test_degradation_is_nan_when_train_objective_is_not_positive():
    """학습 구간에서도 실패한 전략은 '저하율'의 부호가 뒤집혀 엉뚱한 값이 된다."""
    folds = (
        FoldResult(
            fold=Fold(0, START, START, START, END),
            train_metrics=_metrics(sharpe=-1.0), test_metrics=_metrics(sharpe=-2.0),
            test_equity=pd.Series([1.0, 0.9], index=pd.date_range("2023-01-01", periods=2)),
        ),
    )
    summary, _ = build_summary(folds, objective="sharpe", has_grid=False)
    assert math.isnan(summary.degradation)


def test_param_stability_detects_unstable_selection():
    def _fold(i: int, threshold: float) -> FoldResult:
        return FoldResult(
            fold=Fold(i, START, START, START, END),
            params={"rule.price_rule.threshold": threshold},
            train_metrics=_metrics(), test_metrics=_metrics(),
            test_equity=pd.Series([1.0, 1.1], index=pd.date_range("2023-01-01", periods=2)),
        )

    stable, _ = build_summary(
        (_fold(0, 10.0), _fold(1, 10.0)), objective="sharpe", has_grid=True
    )
    unstable, _ = build_summary(
        (_fold(0, 10.0), _fold(1, 20.0)), objective="sharpe", has_grid=True
    )
    assert stable.param_stability == 1.0
    assert unstable.param_stability == 0.5


def test_oos_consistency_is_share_of_profitable_folds():
    def _fold(i: int, total_return: float) -> FoldResult:
        return FoldResult(
            fold=Fold(i, START, START, START, END),
            train_metrics=_metrics(), test_metrics=_metrics(total_return=total_return),
            test_equity=pd.Series([1.0, 1.1], index=pd.date_range("2023-01-01", periods=2)),
        )

    summary, _ = build_summary(
        (_fold(0, 0.2), _fold(1, -0.1), _fold(2, 0.3), _fold(3, -0.05)),
        objective="sharpe", has_grid=False,
    )
    assert summary.oos_consistency == pytest.approx(0.5)


def test_oos_curve_chains_fold_returns_multiplicatively():
    """폴드마다 자기 자본에서 다시 시작하므로 그냥 붙이면 계단이 생긴다."""
    def _fold(i: int, values: list[float], start: str) -> FoldResult:
        return FoldResult(
            fold=Fold(i, START, START, START, END),
            train_metrics=_metrics(), test_metrics=_metrics(),
            test_equity=pd.Series(values, index=pd.date_range(start, periods=len(values))),
        )

    summary, curve = build_summary(
        (
            _fold(0, [100.0, 110.0], "2023-01-01"),   # +10%
            _fold(1, [1000.0, 1200.0], "2023-02-01"),  # +20%
        ),
        objective="sharpe", has_grid=False,
    )
    assert float(curve.iloc[0]) == pytest.approx(1.0)
    assert float(curve.iloc[-1]) == pytest.approx(1.1 * 1.2)
    assert summary.oos_total_return == pytest.approx(0.32)


def test_oos_mdd_is_measured_on_the_composite_curve():
    folds = (
        FoldResult(
            fold=Fold(0, START, START, START, END),
            train_metrics=_metrics(), test_metrics=_metrics(),
            test_equity=pd.Series(
                [100.0, 120.0, 60.0, 90.0], index=pd.date_range("2023-01-01", periods=4)
            ),
        ),
    )
    summary, _ = build_summary(folds, objective="sharpe", has_grid=False)
    assert summary.oos_mdd == pytest.approx(0.5)


# --- 목적함수 ---


def test_objective_calmar_is_return_over_drawdown():
    assert objective_value(_metrics(total_return=0.2, mdd=0.1), "calmar") == pytest.approx(2.0)


def test_calmar_with_zero_drawdown_is_not_selectable():
    """무한대가 승자가 되면 '거의 거래하지 않는 파라미터'가 항상 뽑힌다."""
    assert math.isnan(objective_value(_metrics(mdd=0.0), "calmar"))


def test_unknown_objective_is_rejected_at_spec_construction():
    with pytest.raises(ValidationError, match="미지의 objective"):
        ValidationSpec(objective="omega")


# --- 실패 격리 ---


def test_invalid_combination_is_isolated_and_recorded():
    """특정 조합이 실패해도 나머지 조합으로 폴드를 완성하고 사유만 남긴다."""
    portfolio_defn = StrategyDefinition(
        id="v2", name="v2", version="1",
        factor_refs=(FactorRef("price"),),
        universe=Universe(symbols=("005930",)),
        rule=RuleBinding(entry=("price_rule",)),
        portfolio=PortfolioPolicy(max_positions=1),
    )
    # max_positions=0은 정의 검증에서 거부되므로 그 조합만 실패한다.
    spec = ValidationSpec(mode="holdout", grid={"portfolio.max_positions": [1, 0]})
    report = _run(spec, defn=portfolio_defn)

    fold = report.folds[0]
    assert fold.error == ""  # 유효 조합이 하나라도 있으면 폴드는 성공
    failed = [c for c in fold.candidates if c.error]
    assert len(failed) == 1
    assert failed[0].params == {"portfolio.max_positions": 0}
    assert fold.params == {"portfolio.max_positions": 1}


def test_all_folds_failing_raises_instead_of_empty_report():
    """요약이 전부 NaN인 빈 리포트를 조용히 돌려주면 실패를 알아채지 못한다."""
    empty = {"005930": FactorInput(ohlcv=_ohlcv([100.0] * 40), valuation=None, financials=None)}
    with pytest.raises(ValidationError, match="모든 폴드"):
        run_validation(
            DEFN, empty, spec=ValidationSpec(mode="holdout"),
            start=date(2024, 1, 1), end=date(2024, 12, 31), fees=0.0, slippage=0.0,
            resolve_formula=_resolve_formula, resolve_rule=_resolve_rule,
        )


# --- 스펙 직렬화 ---


def test_spec_roundtrips_through_dict():
    spec = ValidationSpec(
        mode="walkforward", n_folds=4, test_ratio=0.25, anchored=False,
        objective="calmar", grid={"portfolio.max_positions": [3, 5]},
    )
    assert ValidationSpec.from_dict(spec.to_dict()) == spec


def test_spec_rejects_unknown_field():
    with pytest.raises(ValidationError, match="미지의 스펙 필드"):
        ValidationSpec.from_dict({"mode": "holdout", "purge_days": 5})


def test_progress_callback_reports_train_and_test_stages():
    seen: list[tuple[int, str]] = []
    run_validation(
        DEFN, _data(), spec=ValidationSpec(mode="holdout",
                                           grid={"rule.price_rule.threshold": [50.0, 150.0]}),
        start=START, end=END, fees=0.0, slippage=0.0,
        resolve_formula=_resolve_formula, resolve_rule=_resolve_rule,
        on_progress=lambda idx, total, stage, done, of: seen.append((idx, stage)),
    )
    assert seen == [(0, "train"), (0, "train"), (0, "test")]


def test_candidate_serialization_drops_non_finite_values():
    raw = Candidate(params={}, objective=float("nan"), total_return=0.1, mdd=0.0).to_dict()
    assert raw["objective"] is None
    assert raw["total_return"] == pytest.approx(0.1)


def test_bad_grid_address_fails_before_running_folds():
    """주소 오타가 '모든 폴드 실패' 뒤에 파묻히지 않고 즉시 드러나야 한다."""
    spec = ValidationSpec(mode="holdout", grid={"rule.no_such_rule.threshold": [1.0, 2.0]})
    with pytest.raises(ValidationError, match="파라미터 그리드 오류"):
        _run(spec)


def test_unknown_grid_key_is_rejected_upfront():
    spec = ValidationSpec(mode="holdout", grid={"universe.symbols": [["005930"]]})
    with pytest.raises(ValidationError, match="파라미터 그리드 오류"):
        _run(spec)


def test_zero_trade_sweep_reports_the_selector_hint():
    """골든크로스에서 선택자 없이 스윕하면 두 창이 같아져 신호가 영영 발생하지 않는다.

    "목적함수가 모두 NaN"만 돌려주면 원인을 알 수 없으므로, 원인을 짚어 줘야 한다.
    """
    cross = Rule(
        id="cross", name="cross", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), "crosses_above",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    defn = StrategyDefinition(
        id="v3", name="v3", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
        universe=Universe(symbols=("005930",)),
        rule=RuleBinding(entry=("cross",)),
    )
    with pytest.raises(ValidationError, match="선택자가 필요할 수 있습니다"):
        run_validation(
            defn, _data(), spec=ValidationSpec(mode="holdout",
                                               grid={"factor.sma.window": [3, 5, 8]}),
            start=START, end=END, fees=0.0, slippage=0.0,
            resolve_formula=_resolve_formula,
            resolve_rule=lambda rid: cross if rid == "cross" else None,
        )


def test_identical_fold_errors_are_folded_into_one_line():
    """설정 문제는 구간과 무관하게 반복되므로, 폴드 수만큼 늘어나면 정작 읽히지 않는다."""
    empty = {"005930": FactorInput(ohlcv=_ohlcv([100.0] * 40), valuation=None, financials=None)}
    with pytest.raises(ValidationError) as exc:
        run_validation(
            DEFN, empty, spec=ValidationSpec(n_folds=2, test_ratio=0.4),
            start=date(2024, 1, 1), end=date(2024, 12, 31), fees=0.0, slippage=0.0,
            resolve_formula=_resolve_formula, resolve_rule=_resolve_rule,
        )
    assert "폴드1:" not in str(exc.value)
