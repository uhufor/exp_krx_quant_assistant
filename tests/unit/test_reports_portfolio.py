from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.llm.mock_provider import MockProvider
from quant_krx.quant.base import BacktestMetrics, BacktestResult
from quant_krx.reports import ReportARenderer, ReportBRenderer, ReportInput
from quant_krx.signals.classifier import SignalClassifier, SignalType
from quant_krx.signals.rebalance import diff_weights

AS_OF = date(2024, 3, 1)
NAMES = {
    "005930": {"name": "삼성전자"},
    "000660": {"name": "SK하이닉스"},
    "006400": {"name": "삼성SDI"},
}


def _result() -> BacktestResult:
    metrics = BacktestMetrics(
        total_return=0.25, benchmark_return=0.1, excess_return=0.15, mdd=0.12,
        sharpe=1.4, sortino=1.9, trade_count=8, fees_paid=1000.0, slippage_cost=100.0,
        recent_6m_return=0.08, recent_12m_return=0.2, win_rate=0.62,
    )
    return BacktestResult(
        symbol="__portfolio__", strategy_name="pf", strategy_display_name="월간 리밸런싱 전략",
        params={}, start=date(2024, 1, 1), end=AS_OF, metrics=metrics,
        trades=pd.DataFrame(), equity_curve=pd.Series(dtype=float), run_id="run1",
    )


def _input(weights: dict, as_of: date = AS_OF) -> ReportInput:
    plan = diff_weights(weights, as_of)
    signal = SignalClassifier("balanced").classify_portfolio(
        _result(), plan, signal_date=as_of, strategy_display_name="월간 리밸런싱 전략"
    )
    return ReportInput(signal=signal, rebalance_plan=plan, symbol_metadata=NAMES)


REBALANCED = {
    "2024-02-01": {"005930": 0.5, "000660": 0.5},
    "2024-03-01": {"005930": 0.5, "006400": 0.5},
}
UNCHANGED = {
    "2024-02-01": {"005930": 0.5, "000660": 0.5},
    "2024-03-01": {"005930": 0.5, "000660": 0.5},
}


# --- Report A ---


def test_report_a_shows_portfolio_not_symbol():
    report = ReportARenderer().render(_input(REBALANCED))

    assert "포트폴리오 리포트" in report.content
    assert "__portfolio__" not in report.content, "의사 키가 사용자에게 노출되면 안 된다"


def test_report_a_lists_buy_sell_hold_actions():
    report = ReportARenderer().render(_input(REBALANCED))

    assert "전량 매도" in report.content
    assert "000660" in report.content   # 제외 대상
    assert "신규 매수" in report.content
    assert "006400" in report.content   # 편입 대상
    assert "유지" in report.content
    assert "005930" in report.content


def test_report_a_includes_symbol_names():
    report = ReportARenderer().render(_input(REBALANCED))
    assert "삼성SDI" in report.content


def test_report_a_states_holding_assumption():
    """직전 목표 비중을 보유로 가정했다는 사실을 숨기지 않아야 한다(D3)."""
    report = ReportARenderer().render(_input(REBALANCED))
    assert "직전 리밸런싱" in report.content
    assert "가정" in report.content


def test_report_a_no_change_case():
    report = ReportARenderer().render(_input(UNCHANGED))

    assert "현 배분 유지" in report.content
    assert "전량 매도" not in report.content
    assert "신규 매수" not in report.content


def test_report_a_is_deterministic():
    inp = _input(REBALANCED)
    first = ReportARenderer().render(inp)
    second = ReportARenderer().render(inp)
    assert first.content == second.content
    assert first.llm_used is False


def test_report_a_telegram_has_no_pseudo_key():
    report = ReportARenderer().render(_input(REBALANCED))
    assert "__portfolio__" not in report.telegram_content
    assert "매매 지시" in report.telegram_content


def test_report_a_weight_change_is_shown_as_adjustment():
    weights = {
        "2024-02-01": {"005930": 0.3, "000660": 0.7},
        "2024-03-01": {"005930": 0.7, "000660": 0.3},
    }
    report = ReportARenderer().render(_input(weights))
    assert "추가 매수" in report.content
    assert "일부 매도" in report.content


def test_per_symbol_report_still_renders_without_plan():
    """기존 종목별 리포트 경로는 rebalance_plan이 없을 때 그대로 유지된다(회귀)."""
    result = _result()
    result = BacktestResult(**{**result.__dict__, "symbol": "005930"})
    signal = SignalClassifier("balanced").classify(result, signal_date=AS_OF)
    report = ReportARenderer().render(ReportInput(signal=signal, ticker_metadata=NAMES["005930"]))

    assert "퀀트 신호 리포트" in report.content
    assert "삼성전자" in report.content


# --- Report B ---


def test_report_b_prompt_describes_portfolio_not_symbol():
    renderer = ReportBRenderer(llm=MockProvider())
    prompt = renderer._build_prompt(_input(REBALANCED))

    assert "__portfolio__" not in prompt
    assert "포트폴리오" in prompt
    assert "목표 보유 종목" in prompt
    assert "리밸런싱 지시" in prompt


def test_report_b_references_same_signal_id():
    inp = _input(REBALANCED)
    report = ReportBRenderer(llm=MockProvider()).render(inp)

    assert report.signal_id == inp.signal.id
    assert report.report_type == "B"


def test_report_b_prompt_for_per_symbol_unchanged():
    result = BacktestResult(**{**_result().__dict__, "symbol": "005930"})
    signal = SignalClassifier("balanced").classify(result, signal_date=AS_OF)
    prompt = ReportBRenderer(llm=MockProvider())._build_prompt(
        ReportInput(signal=signal, ticker_metadata=NAMES["005930"])
    )
    assert "- 종목: 005930" in prompt


@pytest.mark.parametrize("signal_type", [SignalType.REBALANCE, SignalType.HOLD])
def test_portfolio_signal_types_render(signal_type):
    """두 신호 유형 모두 렌더링이 깨지지 않아야 한다."""
    weights = REBALANCED if signal_type is SignalType.REBALANCE else UNCHANGED
    inp = _input(weights)
    assert inp.signal.signal_type is signal_type
    assert ReportARenderer().render(inp).content


# --- 리밸런싱일이 아닌 날 (지난 지시 반복 방지) ---

LATER = date(2024, 3, 20)


def test_report_a_shows_targets_not_actions_off_rebalance_day():
    """리밸런싱일이 아니면 지나간 매매 지시 대신 목표 배분 현황을 보여야 한다.

    지시를 매일 반복하면 이미 실행한 매매를 다시 하라는 뜻이 되어버린다.
    """
    report = ReportARenderer().render(_input(REBALANCED, as_of=LATER))

    assert "현재 목표 배분" in report.content
    assert "매매 지시" not in report.content
    assert "전량 매도" not in report.content
    assert "신규 매수" not in report.content


def test_report_a_target_rows_list_holdings_with_weights():
    report = ReportARenderer().render(_input(REBALANCED, as_of=LATER))

    # 2024-03-01 리밸런싱 결과(005930 50%, 006400 50%)가 현재 보유 목표다.
    assert "005930" in report.content
    assert "006400" in report.content
    assert "50.0%" in report.content
    assert "000660" not in report.content, "이미 제외된 종목은 목표 배분에 없어야 한다"


def test_report_a_all_cash_state():
    weights = {
        "2024-02-01": {"005930": 1.0},
        "2024-03-01": {},
    }
    report = ReportARenderer().render(_input(weights, as_of=LATER))
    assert "보유 없음(전량 현금)" in report.content


def test_report_a_telegram_matches_section_switch():
    on_day = ReportARenderer().render(_input(REBALANCED))
    off_day = ReportARenderer().render(_input(REBALANCED, as_of=LATER))

    assert "매매 지시" in on_day.telegram_content
    assert "현재 목표 배분" in off_day.telegram_content
    assert "전량 매도" not in off_day.telegram_content
