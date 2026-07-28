from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.factors import FactorInput
from quant_krx.rule.definition import ConstantOperand, FactorOperand, Predicate, Rule
from quant_krx.strategy.definition import (
    FactorRef,
    PortfolioPolicy,
    RankingSpec,
    RuleBinding,
    StrategyDefinition,
    Universe,
)
from quant_krx.workspace.backtest import PORTFOLIO_KEY, run_backtest
from quant_krx.workspace.errors import EvaluationError

SYMBOLS = ["000660", "005930", "006400"]
INITIAL_CASH = 10_000_000.0


def _ohlcv(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes, "high": closes, "low": closes,
            "close": closes, "volume": [10_000.0] * len(closes),
        },
        index=index,
    )


def _rising(n: int, slope: float, base: float = 100.0) -> list[float]:
    return [base + slope * i for i in range(n)]


def _data(series: dict[str, list[float]]) -> dict[str, FactorInput]:
    return {
        symbol: FactorInput(ohlcv=_ohlcv(closes), valuation=None, financials=None)
        for symbol, closes in series.items()
    }


# 항상 참인 진입 규칙(가격 > 0) — 신호 생성이 아니라 배분·자본공유를 검증하기 위한 고정 장치.
ALWAYS_IN = Rule(
    id="always_in", name="always", version="1",
    root=Predicate(FactorOperand("price", "close", {}), ">", ConstantOperand(0.0)),
)


def _resolve_rule(rule_id: str):
    return ALWAYS_IN if rule_id == "always_in" else None


def _resolve_formula(_: str):
    return None


def _defn(policy: PortfolioPolicy | None, factor_refs=None) -> StrategyDefinition:
    return StrategyDefinition(
        id="p1", name="p1", version="1",
        factor_refs=factor_refs or (FactorRef("price"),),
        universe=Universe(symbols=tuple(SYMBOLS)),
        rule=RuleBinding(entry=("always_in",)),
        portfolio=policy,
    )


def _run(policy: PortfolioPolicy | None, series: dict[str, list[float]], **kwargs):
    return run_backtest(
        _defn(policy, factor_refs=kwargs.pop("factor_refs", None)),
        _data(series),
        fees=0.0, slippage=0.0,
        resolve_formula=_resolve_formula, resolve_rule=_resolve_rule,
        **kwargs,
    )


# --- 모드 분기 ---


def test_without_policy_uses_per_symbol_mode():
    """portfolio 미선언 시 기존 종목별 독립 백테스트가 그대로 유지되어야 한다(하위호환)."""
    report = _run(None, {s: _rising(60, 1.0) for s in SYMBOLS})

    assert report.is_portfolio is False
    assert set(report.per_symbol) == set(SYMBOLS)
    assert PORTFOLIO_KEY not in report.results
    assert report.weights == {}


def test_with_policy_uses_portfolio_mode():
    report = _run(
        PortfolioPolicy(max_positions=2, rebalance="monthly"),
        {s: _rising(60, 1.0) for s in SYMBOLS},
    )

    assert report.is_portfolio is True
    assert list(report.results) == [PORTFOLIO_KEY]
    assert report.per_symbol == {}, "자본 공유 모드에서 종목별 독립 성과는 정의되지 않는다"
    assert report.weights


# --- 자본 공유(P1의 존재 이유) ---


def test_capital_is_shared_not_multiplied():
    """3종목 동시 보유해도 총 투입 자본은 initial_cash 하나여야 한다.

    기존 종목별 모드는 종목마다 자본 100%를 가정해 3종목이면 자본이 3배로 부풀려진다.
    """
    policy = PortfolioPolicy(max_positions=3, rebalance="monthly", initial_cash=INITIAL_CASH)
    report = _run(policy, {s: _rising(60, 1.0) for s in SYMBOLS})

    equity = report.results[PORTFOLIO_KEY].equity_curve
    assert equity.iloc[0] == pytest.approx(INITIAL_CASH, rel=1e-6)
    # 전 종목이 동일하게 상승하므로 최종 자산도 initial_cash 배수 범위를 벗어나지 않는다.
    assert equity.iloc[-1] < INITIAL_CASH * 2


def test_max_positions_limits_concurrent_holdings():
    """모든 종목이 진입 신호를 내도 보유 종목 수는 max_positions를 넘지 않는다."""
    policy = PortfolioPolicy(max_positions=2, rebalance="monthly")
    report = _run(policy, {s: _rising(60, 1.0) for s in SYMBOLS})

    for allocation in report.weights.values():
        assert len(allocation) <= 2
        assert sum(allocation.values()) == pytest.approx(1.0)


def test_equal_weight_allocation():
    policy = PortfolioPolicy(max_positions=2, rebalance="monthly")
    report = _run(policy, {s: _rising(60, 1.0) for s in SYMBOLS})

    for allocation in report.weights.values():
        assert all(w == pytest.approx(0.5) for w in allocation.values())


# --- 랭킹 ---


def test_ranking_selects_higher_scoring_symbols():
    """상승률이 다른 3종목 중 SMA 상위 2종목만 담겨야 한다."""
    policy = PortfolioPolicy(
        max_positions=2, rebalance="monthly",
        ranking=RankingSpec(kind="factor", factor_id="sma", column="sma", params={"window": 5}),
    )
    series = {
        "000660": _rising(60, 0.1),   # 가장 완만
        "005930": _rising(60, 1.0),
        "006400": _rising(60, 5.0),   # 가장 가파름
    }
    report = _run(
        policy, series,
        factor_refs=(FactorRef("price"), FactorRef("sma", {"window": 5})),
    )

    last_allocation = report.weights[max(report.weights)]
    assert set(last_allocation) == {"005930", "006400"}


def test_ranking_descending_false_selects_lower_scores():
    policy = PortfolioPolicy(
        max_positions=1, rebalance="monthly",
        ranking=RankingSpec(
            kind="factor", factor_id="sma", column="sma",
            params={"window": 5}, descending=False,
        ),
    )
    series = {
        "000660": _rising(60, 0.1),
        "005930": _rising(60, 1.0),
        "006400": _rising(60, 5.0),
    }
    report = _run(
        policy, series,
        factor_refs=(FactorRef("price"), FactorRef("sma", {"window": 5})),
    )

    last_allocation = report.weights[max(report.weights)]
    assert set(last_allocation) == {"000660"}


def test_ranking_changes_result():
    """랭킹 유무로 결과가 실제로 달라져야 한다(랭킹이 소비되고 있음의 증거)."""
    series = {
        "000660": _rising(60, 0.1),
        "005930": _rising(60, 1.0),
        "006400": _rising(60, 5.0),
    }
    without = _run(PortfolioPolicy(max_positions=1, rebalance="monthly"), series)
    with_ranking = _run(
        PortfolioPolicy(
            max_positions=1, rebalance="monthly",
            ranking=RankingSpec(
                kind="factor", factor_id="sma", column="sma", params={"window": 5}
            ),
        ),
        series,
        factor_refs=(FactorRef("price"), FactorRef("sma", {"window": 5})),
    )

    assert without.metrics.total_return != pytest.approx(with_ranking.metrics.total_return)


# --- 리밸런싱 주기 ---


@pytest.mark.parametrize(
    ("rebalance", "expected"), [("monthly", 4), ("quarterly", 2)]
)
def test_rebalance_frequency_controls_trade_dates(rebalance, expected):
    """2024-01-01부터 100일이면 월간 4구간(1~4월), 분기 2구간(Q1, Q2)."""
    policy = PortfolioPolicy(max_positions=2, rebalance=rebalance)
    report = _run(policy, {s: _rising(100, 1.0) for s in SYMBOLS})
    assert len(report.weights) == expected


def test_weekly_rebalances_more_often_than_monthly():
    series = {s: _rising(100, 1.0) for s in SYMBOLS}
    weekly = _run(PortfolioPolicy(max_positions=2, rebalance="weekly"), series)
    monthly = _run(PortfolioPolicy(max_positions=2, rebalance="monthly"), series)
    assert len(weekly.weights) > len(monthly.weights)


# --- 견고성 ---


def test_symbol_failure_is_isolated():
    """한 종목의 데이터가 비어도 나머지로 포트폴리오가 구성되어야 한다(FR-17)."""
    data = _data({s: _rising(60, 1.0) for s in SYMBOLS})
    data["005930"] = FactorInput(
        ohlcv=pd.DataFrame(columns=["open", "high", "low", "close", "volume"]),
        valuation=None, financials=None,
    )

    report = run_backtest(
        _defn(PortfolioPolicy(max_positions=3, rebalance="monthly")),
        data, fees=0.0, slippage=0.0,
        resolve_formula=_resolve_formula, resolve_rule=_resolve_rule,
    )

    assert "005930" in report.errors
    assert report.is_portfolio is True
    for allocation in report.weights.values():
        assert "005930" not in allocation


def test_date_range_is_respected():
    policy = PortfolioPolicy(max_positions=2, rebalance="monthly")
    report = _run(
        policy, {s: _rising(120, 1.0) for s in SYMBOLS},
        start=date(2024, 2, 1), end=date(2024, 3, 31),
    )

    result = report.results[PORTFOLIO_KEY]
    assert result.start >= date(2024, 2, 1)
    assert result.end <= date(2024, 3, 31)


def test_portfolio_backtest_is_deterministic():
    """동일 입력 → 동일 결과(결정론 불변식 2)."""
    policy = PortfolioPolicy(max_positions=2, rebalance="monthly")
    series = {s: _rising(60, 1.0 + i) for i, s in enumerate(SYMBOLS)}

    first = _run(policy, series)
    second = _run(policy, series)

    assert first.metrics.total_return == pytest.approx(second.metrics.total_return)
    assert first.weights == second.weights


# --- 동적 유니버스 연동 (P2) ---


def _dynamic_defn(policy: PortfolioPolicy) -> StrategyDefinition:
    return StrategyDefinition(
        id="dyn", name="dyn", version="1",
        factor_refs=(FactorRef("price"),),
        universe=Universe(kind="screening", screening_id="cond1"),
        rule=RuleBinding(entry=("always_in",)),
        portfolio=policy,
    )


def _run_dynamic(policy: PortfolioPolicy, series, resolve_universe, **kwargs):
    return run_backtest(
        _dynamic_defn(policy), _data(series),
        fees=0.0, slippage=0.0,
        resolve_formula=_resolve_formula, resolve_rule=_resolve_rule,
        resolve_universe=resolve_universe, **kwargs,
    )


def test_dynamic_universe_restricts_candidates():
    """스크리닝을 통과한 종목만 담겨야 한다."""
    policy = PortfolioPolicy(max_positions=3, rebalance="monthly")
    only_one = lambda _cond, _as_of: ["005930"]  # noqa: E731

    report = _run_dynamic(policy, {s: _rising(90, 1.0) for s in SYMBOLS}, only_one)

    for allocation in report.weights.values():
        assert set(allocation) <= {"005930"}


def test_dynamic_universe_changes_over_time():
    """시점마다 다른 종목이 선택되면 배분도 따라 바뀌어야 한다."""
    policy = PortfolioPolicy(max_positions=1, rebalance="monthly")

    def _resolve(_cond, as_of):
        return ["005930"] if as_of.month <= 2 else ["006400"]

    report = _run_dynamic(policy, {s: _rising(120, 1.0) for s in SYMBOLS}, _resolve)

    dates = sorted(report.weights)
    early = report.weights[dates[0]]
    late = report.weights[dates[-1]]
    assert set(early) == {"005930"}
    assert set(late) == {"006400"}


def test_dynamic_universe_empty_period_holds_nothing():
    """어느 시점에 통과 종목이 0이면 그 구간은 보유가 없어야 한다."""
    policy = PortfolioPolicy(max_positions=2, rebalance="monthly")

    def _resolve(_cond, as_of):
        return [] if as_of.month == 2 else ["005930"]

    report = _run_dynamic(policy, {s: _rising(120, 1.0) for s in SYMBOLS}, _resolve)

    february = [d for d in report.weights if d.startswith("2024-02")]
    assert february, "2월 리밸런싱이 존재해야 한다"
    for date_key in february:
        assert report.weights[date_key] == {}


def test_dynamic_universe_without_resolver_fails_clearly():
    """리졸버 없이 동적 유니버스를 실행하면 조용히 전체 종목을 쓰지 않고 명확히 실패한다."""
    policy = PortfolioPolicy(max_positions=2, rebalance="monthly")
    with pytest.raises(EvaluationError, match="유니버스 리졸버가 주입되지"):
        run_backtest(
            _dynamic_defn(policy), _data({s: _rising(60, 1.0) for s in SYMBOLS}),
            fees=0.0, slippage=0.0,
            resolve_formula=_resolve_formula, resolve_rule=_resolve_rule,
        )


def test_dynamic_universe_resolver_called_once_per_rebalance_date():
    """같은 리밸런싱일에 대해 스크리닝을 중복 호출하지 않는다(엔진 내 캐시)."""
    policy = PortfolioPolicy(max_positions=2, rebalance="monthly")
    calls: list[date] = []

    def _resolve(_cond, as_of):
        calls.append(as_of)
        return ["005930"]

    report = _run_dynamic(policy, {s: _rising(120, 1.0) for s in SYMBOLS}, _resolve)

    assert len(calls) == len(report.weights)
    assert len(calls) == len(set(calls))
