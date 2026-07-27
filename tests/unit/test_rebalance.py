from __future__ import annotations

from datetime import date

import pytest

from quant_krx.signals.rebalance import diff_weights

AS_OF = date(2024, 3, 1)


def test_first_entry_has_no_previous_holdings():
    """최초 리밸런싱은 직전 배분이 없으므로 전부 신규 편입이다."""
    plan = diff_weights({"2024-03-01": {"005930": 0.5, "000660": 0.5}}, AS_OF)

    assert plan.previous_date is None
    assert [c.symbol for c in plan.entries] == ["000660", "005930"]
    assert plan.exits == ()
    assert plan.holds == ()
    assert plan.is_rebalance_day is True


def test_classifies_entries_exits_and_holds():
    weights = {
        "2024-02-01": {"005930": 0.5, "000660": 0.5},
        "2024-03-01": {"005930": 0.5, "006400": 0.5},
    }
    plan = diff_weights(weights, AS_OF)

    assert [c.symbol for c in plan.entries] == ["006400"]
    assert [c.symbol for c in plan.exits] == ["000660"]
    assert [c.symbol for c in plan.holds] == ["005930"]


def test_hold_carries_weight_change():
    weights = {
        "2024-02-01": {"005930": 0.3, "000660": 0.7},
        "2024-03-01": {"005930": 0.6, "000660": 0.4},
    }
    plan = diff_weights(weights, AS_OF)

    changes = {c.symbol: c for c in plan.holds}
    assert changes["005930"].delta == pytest.approx(0.3)
    assert changes["000660"].delta == pytest.approx(-0.3)
    assert plan.has_changes is True


def test_identical_weights_report_no_changes():
    weights = {
        "2024-02-01": {"005930": 0.5, "000660": 0.5},
        "2024-03-01": {"005930": 0.5, "000660": 0.5},
    }
    plan = diff_weights(weights, AS_OF)

    assert plan.entries == ()
    assert plan.exits == ()
    assert plan.has_changes is False
    assert "변경 없음" in plan.summary()


def test_full_liquidation_marks_all_as_exit():
    weights = {
        "2024-02-01": {"005930": 0.5, "000660": 0.5},
        "2024-03-01": {},
    }
    plan = diff_weights(weights, AS_OF)

    assert [c.symbol for c in plan.exits] == ["000660", "005930"]
    assert plan.entries == ()
    assert plan.target_symbols == ()
    assert plan.has_changes is True


def test_not_rebalance_day_when_last_rebalance_is_past():
    weights = {
        "2024-02-01": {"005930": 1.0},
        "2024-03-01": {"005930": 1.0},
    }
    plan = diff_weights(weights, date(2024, 3, 15))

    assert plan.is_rebalance_day is False
    assert plan.rebalance_date == date(2024, 3, 1)


def test_future_rebalance_dates_are_ignored():
    """as_of 이후 배분은 아직 오지 않은 미래이므로 반영하지 않는다."""
    weights = {
        "2024-03-01": {"005930": 1.0},
        "2024-04-01": {"006400": 1.0},
    }
    plan = diff_weights(weights, AS_OF)

    assert plan.rebalance_date == date(2024, 3, 1)
    assert plan.target_symbols == ("005930",)


def test_empty_weights_is_handled():
    plan = diff_weights({}, AS_OF)

    assert plan.rebalance_date is None
    assert plan.is_rebalance_day is False
    assert plan.has_changes is False
    assert "리밸런싱 이력" in plan.summary()


def test_target_symbols_covers_entries_and_holds():
    weights = {
        "2024-02-01": {"005930": 1.0},
        "2024-03-01": {"005930": 0.5, "006400": 0.5},
    }
    plan = diff_weights(weights, AS_OF)
    assert plan.target_symbols == ("005930", "006400")


def test_summary_counts_each_bucket():
    weights = {
        "2024-02-01": {"005930": 0.5, "000660": 0.5},
        "2024-03-01": {"005930": 0.5, "006400": 0.5},
    }
    summary = diff_weights(weights, AS_OF).summary()

    assert "신규 편입 1" in summary
    assert "제외 1" in summary
    assert "유지 1" in summary


def test_equal_weight_rounding_is_not_treated_as_change():
    """1/3 같은 표현 오차를 비중 변화로 오인하면 매일 '변경 있음'이 된다."""
    third = 1.0 / 3.0
    weights = {
        "2024-02-01": {"a": third, "b": third, "c": third},
        "2024-03-01": {"a": third, "b": third, "c": third},
    }
    plan = diff_weights(
        {k: {s: float(f"{w:.17f}") for s, w in v.items()} for k, v in weights.items()},
        AS_OF,
    )
    assert plan.has_changes is False


# --- 포트폴리오 신호 생성 (R05) ---


def _metrics(**overrides):
    from quant_krx.quant.base import BacktestMetrics

    base = dict(
        total_return=0.2, benchmark_return=0.1, excess_return=0.1, mdd=0.1,
        sharpe=1.5, sortino=2.0, trade_count=10, fees_paid=100.0, slippage_cost=10.0,
        recent_6m_return=0.05, recent_12m_return=0.1, win_rate=0.6,
    )
    base.update(overrides)
    return BacktestMetrics(**base)


def _result(run_id="run1"):
    import pandas as pd

    from quant_krx.quant.base import BacktestResult

    return BacktestResult(
        symbol="__portfolio__", strategy_name="pf", strategy_display_name="포트폴리오 전략",
        params={}, start=date(2024, 1, 1), end=AS_OF, metrics=_metrics(),
        trades=pd.DataFrame(), equity_curve=pd.Series(dtype=float), run_id=run_id,
    )


def _classifier():
    from quant_krx.signals.classifier import SignalClassifier

    return SignalClassifier("balanced")


def test_portfolio_signal_on_rebalance_day_with_changes():
    from quant_krx.signals.classifier import PORTFOLIO_SYMBOL, SignalType

    plan = diff_weights(
        {"2024-02-01": {"005930": 1.0}, "2024-03-01": {"006400": 1.0}}, AS_OF
    )
    signal = _classifier().classify_portfolio(_result(), plan, signal_date=AS_OF)

    assert signal.signal_type is SignalType.REBALANCE
    assert signal.symbol == PORTFOLIO_SYMBOL
    assert "리밸런싱 실행" in signal.position_recommendation


def test_portfolio_signal_holds_when_not_rebalance_day():
    from quant_krx.signals.classifier import SignalType

    plan = diff_weights(
        {"2024-02-01": {"005930": 1.0}, "2024-03-01": {"006400": 1.0}}, date(2024, 3, 20)
    )
    signal = _classifier().classify_portfolio(_result(), plan, signal_date=date(2024, 3, 20))

    assert signal.signal_type is SignalType.HOLD
    assert "현 배분 유지" in signal.position_recommendation


def test_portfolio_signal_holds_when_no_changes():
    """리밸런싱일이어도 배분이 그대로면 매매가 필요 없다."""
    from quant_krx.signals.classifier import SignalType

    plan = diff_weights(
        {"2024-02-01": {"005930": 1.0}, "2024-03-01": {"005930": 1.0}}, AS_OF
    )
    signal = _classifier().classify_portfolio(_result(), plan, signal_date=AS_OF)

    assert signal.signal_type is SignalType.HOLD


def test_portfolio_signal_uses_portfolio_metrics():
    plan = diff_weights({"2024-03-01": {"005930": 1.0}}, AS_OF)
    signal = _classifier().classify_portfolio(_result(), plan, signal_date=AS_OF)

    assert signal.evidence_metrics.total_return == 0.2
    assert signal.evidence_metrics.sharpe == 1.5


def test_portfolio_signal_symbol_matches_backtest_portfolio_key():
    """signals/와 workspace/가 각자 정의한 의사 키가 어긋나면 리포트·조회가 깨진다."""
    from quant_krx.signals.classifier import PORTFOLIO_SYMBOL
    from quant_krx.workspace.backtest import PORTFOLIO_KEY

    assert PORTFOLIO_SYMBOL == PORTFOLIO_KEY


def test_portfolio_signal_is_deterministic_except_id():
    plan = diff_weights({"2024-03-01": {"005930": 1.0}}, AS_OF)
    clf = _classifier()
    first = clf.classify_portfolio(_result(), plan, signal_date=AS_OF)
    second = clf.classify_portfolio(_result(), plan, signal_date=AS_OF)

    assert first.score == second.score
    assert first.signal_type == second.signal_type
    assert first.position_recommendation == second.position_recommendation
