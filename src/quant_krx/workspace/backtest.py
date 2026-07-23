from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import vectorbt as vbt

from quant_krx.factors import FactorInput
from quant_krx.quant.base import BacktestMetrics
from quant_krx.quant.base import BacktestResult as QuantBacktestResult
from quant_krx.quant.metrics import extract_metrics
from quant_krx.strategy.definition import StrategyDefinition
from quant_krx.workspace.errors import EvaluationError
from quant_krx.workspace.evaluation import (
    EvaluationContext,
    FormulaResolver,
    RuleResolver,
    check_data_contract,
    evaluate_rule,
)


@dataclass(frozen=True)
class BacktestReport:
    metrics: BacktestMetrics
    per_symbol: dict[str, BacktestMetrics]
    benchmark: str | None = None
    benchmark_note: str | None = None
    results: dict[str, QuantBacktestResult] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def _combine_and(rule_ids: tuple[str, ...], ctx: EvaluationContext) -> pd.Series:
    assert ctx.resolve_rule is not None
    result: pd.Series | None = None
    for rule_id in rule_ids:
        rule = ctx.resolve_rule(rule_id)
        if rule is None:
            raise EvaluationError(f"미존재 rule_id '{rule_id}'을(를) 참조하고 있습니다")
        series = evaluate_rule(rule, ctx)
        result = series if result is None else (result & series)
    return result


def build_signals(defn: StrategyDefinition, ctx: EvaluationContext) -> tuple[pd.Series, pd.Series]:
    """roles 슬롯 소비 — entry AND 결합→entries, exit AND 결합(부재 시 all False)→exits(FR-10)."""
    if defn.rule is None:
        raise EvaluationError(f"전략 '{defn.id}'은(는) 초안(rule=None) 상태로 백테스트 불가")
    if ctx.resolve_rule is None:
        raise EvaluationError("build_signals에는 resolve_rule 리졸버가 필요합니다")
    check_data_contract(defn, ctx, ctx.resolve_rule)  # FR-09 — 평가 전 데이터 계약 게이트

    entries = _combine_and(tuple(defn.rule.entry), ctx)
    exits = (
        _combine_and(tuple(defn.rule.exit), ctx)
        if defn.rule.exit
        else pd.Series(False, index=ctx.index)
    )
    return entries, exits


def run_single_symbol_backtest(
    defn: StrategyDefinition,
    symbol: str,
    factor_input: FactorInput,
    *,
    fees: float,
    slippage: float,
    benchmark: pd.DataFrame | None,
    resolve_formula: FormulaResolver,
    resolve_rule: RuleResolver,
    start: date | None = None,
    end: date | None = None,
    run_id: str = "",
) -> QuantBacktestResult:
    """단일 (전략, 종목) baseline 엔진 위임 — quant.base.BacktestResult 반환(FR-18)."""
    ohlcv = factor_input.ohlcv
    if start is not None:
        ohlcv = ohlcv.loc[ohlcv.index >= pd.Timestamp(start)]
    if end is not None:
        ohlcv = ohlcv.loc[ohlcv.index <= pd.Timestamp(end)]

    ctx = EvaluationContext(
        data=factor_input, index=ohlcv.index,
        resolve_formula=resolve_formula, resolve_rule=resolve_rule,
    )
    entries, exits = build_signals(defn, ctx)
    close = ohlcv["close"].astype(float)

    pf = vbt.Portfolio.from_signals(close, entries, exits, fees=fees, slippage=slippage, freq="D")
    metrics = extract_metrics(pf, close, benchmark, fees, slippage)
    trades_df = (
        pf.trades.records_readable if hasattr(pf.trades, "records_readable") else pd.DataFrame()
    )

    return QuantBacktestResult(
        symbol=symbol,
        strategy_name=defn.id,
        strategy_display_name=defn.name,
        params={},
        start=close.index[0].date(),
        end=close.index[-1].date(),
        metrics=metrics,
        trades=trades_df,
        equity_curve=pf.value(),
        run_id=run_id,
        price=close,
    )


def run_backtest(
    defn: StrategyDefinition,
    data: dict[str, FactorInput],
    *,
    fees: float,
    slippage: float,
    benchmark: pd.DataFrame | None = None,
    resolve_formula: FormulaResolver,
    resolve_rule: RuleResolver,
    start: date | None = None,
    end: date | None = None,
) -> BacktestReport:
    """종목별 (close, entries, exits, fees, slippage)를 baseline 엔진에 위임(FR-11/12).

    jobs/daily.py와 동일한 종목 단위 실패 격리(FR-17) — 밸류에이션이 없는 ETF처럼
    특정 종목이 데이터 계약을 못 채우거나 평가 중 실패해도, 나머지 종목 결과는
    그대로 반환하고 실패 사유만 errors에 기록한다(배치 전체를 막지 않음).
    """
    results: dict[str, QuantBacktestResult] = {}
    errors: dict[str, str] = {}
    for symbol, factor_input in data.items():
        try:
            results[symbol] = run_single_symbol_backtest(
                defn, symbol, factor_input,
                fees=fees, slippage=slippage, benchmark=benchmark,
                resolve_formula=resolve_formula, resolve_rule=resolve_rule, start=start, end=end,
            )
        except Exception as e:  # noqa: BLE001 — 종목 단위 격리(FR-17), 사유는 errors에 보존
            errors[symbol] = str(e)

    if not results:
        detail = "; ".join(f"{s}: {m}" for s, m in errors.items()) or "원인 불명"
        raise EvaluationError(f"모든 종목의 백테스트가 실패했습니다({detail})")

    per_symbol: dict[str, BacktestMetrics] = {
        symbol: result.metrics for symbol, result in results.items()
    }
    # 대표(top-level) 지표: 단일 종목 백테스트가 통상 사용 경로이므로 첫 종목을 대표로 사용.
    representative = next(iter(per_symbol.values()))
    return BacktestReport(
        metrics=representative, per_symbol=per_symbol, results=results, errors=errors
    )
