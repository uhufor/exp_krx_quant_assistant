from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
import vectorbt as vbt

from quant_krx.factors import FactorInput
from quant_krx.quant.base import BacktestMetrics
from quant_krx.quant.base import BacktestResult as QuantBacktestResult
from quant_krx.quant.metrics import extract_metrics
from quant_krx.strategy.definition import RankingSpec, StrategyDefinition
from quant_krx.workspace.errors import EvaluationError
from quant_krx.workspace.evaluation import (
    EvaluationContext,
    FormulaResolver,
    RuleResolver,
    _eval_factor_operand,
    _eval_formula_ref,
    check_data_contract,
    evaluate_rule,
)
from quant_krx.workspace.portfolio import build_target_weights

# 포트폴리오 모드 결과의 results/키 — 종목 코드와 충돌하지 않도록 6자리 숫자 형식을 피한다.
PORTFOLIO_KEY = "__portfolio__"


@dataclass(frozen=True)
class BacktestReport:
    metrics: BacktestMetrics
    per_symbol: dict[str, BacktestMetrics]
    benchmark: str | None = None
    benchmark_note: str | None = None
    results: dict[str, QuantBacktestResult] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    # --- 실행 이력(P3) — run_backtest 자체는 채우지 않고 WorkspaceService가 부여한다.
    # from_cache=True면 저장된 이력에서 복원된 리포트이며 results[*].trades는 항상 비어 있다.
    run_id: str = ""
    executed_at: datetime | None = None
    from_cache: bool = False
    # --- 포트폴리오 모드(P1). is_portfolio=True면 results는 PORTFOLIO_KEY 하나뿐이고
    # per_symbol은 비어 있다 — 자본을 공유하므로 종목별 독립 성과가 정의되지 않기 때문이다.
    # weights는 리밸런싱일별 목표 비중({"YYYY-MM-DD": {symbol: 비중}}, 0 비중은 생략).
    is_portfolio: bool = False
    weights: dict[str, dict[str, float]] = field(default_factory=dict)


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


def _slice_ohlcv(ohlcv: pd.DataFrame, start: date | None, end: date | None) -> pd.DataFrame:
    if start is not None:
        ohlcv = ohlcv.loc[ohlcv.index >= pd.Timestamp(start)]
    if end is not None:
        ohlcv = ohlcv.loc[ohlcv.index <= pd.Timestamp(end)]
    return ohlcv


def _eval_ranking_scores(
    ranking: RankingSpec, ctx: EvaluationContext
) -> pd.Series:
    """RankingSpec을 실제 시계열 값으로 평가한다.

    `strategy/`는 `rule/`을 import하지 않으므로 RankingSpec은 형상만 자체 정의되어 있고,
    두 계층을 모두 아는 이 곳에서 기존 평가기에 위임한다(평가 로직 중복 없음).
    """
    if ranking.kind == "factor":
        return _eval_factor_operand(
            ranking.factor_id, ranking.column, dict(ranking.params), ctx
        )
    if ranking.kind == "formula":
        return _eval_formula_ref(ranking.formula_id, ctx)
    raise EvaluationError(f"미지의 ranking.kind '{ranking.kind}'")


def run_portfolio_backtest(
    defn: StrategyDefinition,
    data: dict[str, FactorInput],
    *,
    fees: float,
    slippage: float,
    benchmark: pd.DataFrame | None,
    resolve_formula: FormulaResolver,
    resolve_rule: RuleResolver,
    start: date | None = None,
    end: date | None = None,
    run_id: str = "",
) -> BacktestReport:
    """자본을 공유하는 다종목 백테스트(P1).

    종목별 신호를 목표 비중 행렬로 변환(`workspace/portfolio.py`)한 뒤 vectorbt에
    `from_orders(size_type='targetpercent', cash_sharing=True)`로 한 번에 넘긴다 —
    종목마다 따로 돌린 뒤 합산하는 기존 경로와 달리 "3종목 동시 진입 시 자본이 어떻게
    쪼개지는가"가 실제로 표현된다.
    """
    policy = defn.portfolio
    assert policy is not None  # 호출부(run_backtest)가 이미 분기했다

    closes: dict[str, pd.Series] = {}
    entries_by_symbol: dict[str, pd.Series] = {}
    exits_by_symbol: dict[str, pd.Series] = {}
    scores_by_symbol: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}

    for symbol, factor_input in sorted(data.items()):
        try:
            ohlcv = _slice_ohlcv(factor_input.ohlcv, start, end)
            if ohlcv.empty:
                raise EvaluationError("해당 기간에 OHLCV 데이터가 없습니다")
            ctx = EvaluationContext(
                data=factor_input, index=ohlcv.index,
                resolve_formula=resolve_formula, resolve_rule=resolve_rule,
            )
            entries, exits = build_signals(defn, ctx)
            closes[symbol] = ohlcv["close"].astype(float)
            entries_by_symbol[symbol] = entries
            exits_by_symbol[symbol] = exits
            if policy.ranking is not None:
                scores_by_symbol[symbol] = _eval_ranking_scores(policy.ranking, ctx)
        except Exception as e:  # noqa: BLE001 — 종목 단위 격리(FR-17), 사유는 errors에 보존
            errors[symbol] = str(e)

    if not closes:
        detail = "; ".join(f"{s}: {m}" for s, m in errors.items()) or "원인 불명"
        raise EvaluationError(f"모든 종목의 백테스트가 실패했습니다({detail})")

    # 종목마다 상장일·데이터 결손이 달라 인덱스가 어긋날 수 있으므로 합집합으로 정렬한다.
    # 가격은 ffill로 메우되, 원래 데이터가 없던 구간은 tradable=False로 후보에서 제외해
    # "아직 상장도 안 한 종목을 매수"하는 일이 없게 한다.
    close_df = pd.DataFrame(closes).sort_index()
    index = close_df.index
    tradable = close_df.notna()
    close_df = close_df.ffill().bfill()

    entries_df = pd.DataFrame(entries_by_symbol).reindex(index).fillna(False).astype(bool)
    exits_df = pd.DataFrame(exits_by_symbol).reindex(index).fillna(False).astype(bool)
    ranking_scores = (
        pd.DataFrame(scores_by_symbol).reindex(index) if scores_by_symbol else None
    )

    weights = build_target_weights(
        entries_df, exits_df, policy, ranking_scores=ranking_scores, tradable=tradable
    )

    pf = vbt.Portfolio.from_orders(
        close_df, size=weights, size_type="targetpercent",
        group_by=True, cash_sharing=True,
        call_seq="auto",  # 매도를 먼저 체결해 매수에 쓸 현금을 확보(그렇지 않으면 주문이 잘림)
        fees=fees, slippage=slippage, init_cash=policy.initial_cash, freq="D",
    )

    # 벤치마크 슬라이싱은 인덱스만 쓰므로 대표 종가 시리즈를 넘긴다(기존 메트릭 추출 재사용).
    representative_close = close_df.iloc[:, 0]
    metrics = extract_metrics(pf, representative_close, benchmark, fees, slippage)

    equity = pf.value()
    if isinstance(equity, pd.DataFrame):  # group_by=True면 통상 Series지만 방어적으로 축약
        equity = equity.iloc[:, 0]

    portfolio_result = QuantBacktestResult(
        symbol=PORTFOLIO_KEY,
        strategy_name=defn.id,
        strategy_display_name=defn.name,
        params={},
        start=index[0].date(),
        end=index[-1].date(),
        metrics=metrics,
        trades=(
            pf.trades.records_readable if hasattr(pf.trades, "records_readable") else pd.DataFrame()
        ),
        equity_curve=equity,
        run_id=run_id,
        price=representative_close,
    )

    return BacktestReport(
        metrics=metrics,
        per_symbol={},  # 자본 공유 모드에서는 종목별 독립 성과가 정의되지 않는다(아래 주석)
        results={PORTFOLIO_KEY: portfolio_result},
        errors=errors,
        weights={
            str(ts.date()): {
                symbol: float(value)
                for symbol, value in row.items()
                if pd.notna(value) and value > 0
            }
            for ts, row in weights.dropna(how="all").iterrows()
        },
        is_portfolio=True,
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

    전략에 portfolio 정책이 선언되어 있으면 자본 공유 다종목 모드로 분기한다(P1).
    """
    if defn.portfolio is not None:
        return run_portfolio_backtest(
            defn, data,
            fees=fees, slippage=slippage, benchmark=benchmark,
            resolve_formula=resolve_formula, resolve_rule=resolve_rule, start=start, end=end,
        )

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
