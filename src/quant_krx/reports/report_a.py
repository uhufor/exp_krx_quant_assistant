from __future__ import annotations

import html as html_mod
import math

from quant_krx.signals.classifier import SignalType

from .base import RenderedReport, ReportInput, display_symbol, now_kst

_SIGNAL_LABEL = {
    SignalType.BUY: "🟢 매수",
    SignalType.SELL: "🔴 매도",
    SignalType.HOLD: "🟡 보유",
    SignalType.WATCH: "🟠 관망",
    SignalType.NO_SIGNAL: "⚪ 신호없음",
}


class ReportARenderer:
    """
    Report A: 순수 퀀트 결과 기반 결정론적 리포트.
    LLM 호출 없음. 외부 컨텍스트 없음.
    같은 Signal 입력 → 항상 같은 출력.
    """

    def render(self, inp: ReportInput, seq: int = 1) -> RenderedReport:
        if inp.rebalance_plan is not None:
            return self._render_portfolio(inp, seq)

        sig = inp.signal
        m = sig.evidence_metrics

        def fmt_pct(v: float) -> str:
            return f"{v:.2%}" if not math.isnan(v) else "N/A"

        def fmt_f(v: float, decimals: int = 2) -> str:
            return f"{v:.{decimals}f}" if not math.isnan(v) else "N/A"

        signal_emoji = _SIGNAL_LABEL.get(sig.signal_type, str(sig.signal_type.value))
        sym_display = display_symbol(sig.symbol, inp.ticker_metadata)
        bm_note = f" ({m.benchmark_note})" if m.benchmark_note else ""

        risk_section = ""
        if sig.risk_flags:
            flags = "\n".join(f"- {f}" for f in sig.risk_flags)
            risk_section = f"\n### 리스크 플래그\n{flags}\n"

        content = f"""# [Report A] {sym_display} 퀀트 신호 리포트
> **리포트 유형**: A (순수 퀀트 — LLM 미사용)
> **신호 ID**: `{sig.id}`
> **실행 ID**: `{sig.run_id}`
> **생성 일시**: {now_kst().strftime('%Y-%m-%d %H:%M KST')}

---

## 신호 요약

| 항목 | 값 |
|------|----|
| 종목 | {sym_display} |
| 날짜 | {sig.signal_date} |
| 신호 | **{signal_emoji}** |
| 전략 | {sig.strategy_display_name} |
| 점수 | {sig.score:.4f} / 1.0 |
| 권고 | {sig.position_recommendation} |

---

## 백테스트 성과 지표

| 지표 | 값 |
|------|----|
| 총 수익률 | {fmt_pct(m.total_return)} |
| 벤치마크 수익률 | {fmt_pct(m.benchmark_return)}{bm_note} |
| 초과 수익률 | {fmt_pct(m.excess_return)} |
| 최대 낙폭 (MDD) | {fmt_pct(m.mdd)} |
| Sharpe Ratio | {fmt_f(m.sharpe)} |
| Sortino Ratio | {fmt_f(m.sortino)} |
| 거래 횟수 | {m.trade_count} |
| 수수료 합계 | {fmt_pct(m.fees_paid)} |
| 최근 6개월 수익률 | {fmt_pct(m.recent_6m_return)} |
| 최근 12개월 수익률 | {fmt_pct(m.recent_12m_return)} |
| 승률 | {fmt_pct(m.win_rate)} |
{risk_section}"""
        return RenderedReport(
            signal_id=sig.id,
            report_type="A",
            content=content.strip(),
            telegram_content=self._render_telegram(inp, seq),
            llm_used=False,
        )

    # --- 포트폴리오 전략(R05) ---

    def _render_portfolio(self, inp: ReportInput, seq: int) -> RenderedReport:
        sig = inp.signal
        plan = inp.rebalance_plan
        m = sig.evidence_metrics
        assert plan is not None

        def fmt_pct(v: float) -> str:
            return f"{v:.2%}" if not math.isnan(v) else "N/A"

        def fmt_f(v: float, decimals: int = 2) -> str:
            return f"{v:.{decimals}f}" if not math.isnan(v) else "N/A"

        header = (
            "🔁 리밸런싱 필요" if sig.signal_type is SignalType.REBALANCE else "🟡 현 배분 유지"
        )
        rebalance_line = (
            f"{plan.rebalance_date} (오늘)"
            if plan.is_rebalance_day
            else f"{plan.rebalance_date}" if plan.rebalance_date else "없음"
        )

        # 매매 지시는 리밸런싱 당일에만 유효하다 — 지나간 리밸런싱의 지시를 매일 반복하면
        # 이미 실행한 매매를 다시 하라는 뜻이 되어버린다. 다른 날은 목표 배분 현황만 보인다.
        if plan.is_rebalance_day:
            section_title = "매매 지시"
            rows = self._action_rows(plan, inp.symbol_metadata)
            fallback = "변경 없음"
        else:
            section_title = "현재 목표 배분"
            rows = self._holding_rows(plan, inp.symbol_metadata)
            fallback = "보유 없음(전량 현금)"
        body = "\n".join(f"| {r} |" for r in rows) if rows else f"| {fallback} |"

        content = f"""# [Report A] {sig.strategy_display_name} 포트폴리오 리포트
> **리포트 유형**: A (순수 퀀트 — LLM 미사용)
> **신호 ID**: `{sig.id}`
> **실행 ID**: `{sig.run_id}`
> **생성 일시**: {now_kst().strftime('%Y-%m-%d %H:%M KST')}

---

## 포트폴리오 요약

| 항목 | 값 |
|------|----|
| 전략 | {sig.strategy_display_name} |
| 날짜 | {sig.signal_date} |
| 상태 | **{header}** |
| 최근 리밸런싱 | {rebalance_line} |
| 점수 | {sig.score:.4f} / 1.0 |
| 권고 | {sig.position_recommendation} |

---

## {section_title}

| 내용 |
|------|
{body}

> 현재 보유는 **직전 리밸런싱({plan.previous_date or "없음"}) 목표 비중**으로 가정했습니다.
> 실제 계좌 잔고와 다를 수 있으니 주문 전 확인하십시오.

---

## 포트폴리오 성과 지표

| 지표 | 값 |
|------|----|
| 총 수익률 | {fmt_pct(m.total_return)} |
| 벤치마크 수익률 | {fmt_pct(m.benchmark_return)} |
| 초과 수익률 | {fmt_pct(m.excess_return)} |
| 최대 낙폭 (MDD) | {fmt_pct(m.mdd)} |
| Sharpe Ratio | {fmt_f(m.sharpe)} |
| Sortino Ratio | {fmt_f(m.sortino)} |
| 거래 횟수 | {m.trade_count} |
| 승률 | {fmt_pct(m.win_rate)} |
"""
        return RenderedReport(
            signal_id=sig.id,
            report_type="A",
            content=content.strip(),
            telegram_content=self._render_portfolio_telegram(inp, seq),
            llm_used=False,
        )

    @staticmethod
    def _holding_rows(plan, symbol_metadata: dict) -> list[str]:
        """리밸런싱일이 아닌 날 보여줄 목표 배분 현황."""

        def label(symbol: str) -> str:
            name = symbol_metadata.get(symbol, {}).get("name", "")
            return f"{symbol} - {name}" if name else symbol

        return [
            f"⚪ {label(c.symbol)} · {c.target_weight:.1%}" for c in plan.targets
        ]

    @staticmethod
    def _action_rows(plan, symbol_metadata: dict) -> list[str]:
        """매매 지시 문자열 목록 — 매도를 먼저 놓는다(현금 확보가 선행돼야 하므로)."""

        def label(symbol: str) -> str:
            name = symbol_metadata.get(symbol, {}).get("name", "")
            return f"{symbol} - {name}" if name else symbol

        rows: list[str] = []
        for change in plan.exits:
            rows.append(f"🔴 전량 매도 · {label(change.symbol)} (기존 {change.current_weight:.1%})")
        for change in plan.entries:
            rows.append(f"🟢 신규 매수 · {label(change.symbol)} (목표 {change.target_weight:.1%})")
        for change in plan.holds:
            if abs(change.delta) <= 1e-9:
                rows.append(f"⚪ 유지 · {label(change.symbol)} ({change.target_weight:.1%})")
            else:
                direction = "추가 매수" if change.delta > 0 else "일부 매도"
                rows.append(
                    f"🔵 {direction} · {label(change.symbol)} "
                    f"({change.current_weight:.1%} → {change.target_weight:.1%})"
                )
        return rows

    def _render_portfolio_telegram(self, inp: ReportInput, seq: int) -> str:
        sig = inp.signal
        plan = inp.rebalance_plan
        m = sig.evidence_metrics
        assert plan is not None

        def fmt_pct(v: float, sign: bool = True) -> str:
            if math.isnan(v):
                return "N/A"
            return f"{v:+.2%}" if sign else f"{v:.2%}"

        strategy = html_mod.escape(sig.strategy_display_name)
        date_str = now_kst().strftime("%Y-%m-%d %H:%M KST") + f" #{seq}"
        header = (
            "🔁 리밸런싱 필요" if sig.signal_type is SignalType.REBALANCE else "🟡 현 배분 유지"
        )

        summary = (
            f"전략:  {strategy}\n"
            f"날짜:  {sig.signal_date}\n"
            f"상태:  {header}\n"
            f"권고:  {html_mod.escape(sig.position_recommendation)}"
        )
        if plan.is_rebalance_day:
            section_title = "매매 지시"
            rows = self._action_rows(plan, inp.symbol_metadata)
            fallback = "변경 없음"
        else:
            section_title = "현재 목표 배분"
            rows = self._holding_rows(plan, inp.symbol_metadata)
            fallback = "보유 없음(전량 현금)"
        body = html_mod.escape("\n".join(rows)) if rows else fallback
        metrics = (
            f"총수익률:  {fmt_pct(m.total_return)}\n"
            f"초과수익:  {fmt_pct(m.excess_return)}\n"
            f"MDD:      {'-' + format(m.mdd, '.2%') if not math.isnan(m.mdd) else 'N/A'}\n"
            f"Sharpe:   {format(m.sharpe, '.2f') if not math.isnan(m.sharpe) else 'N/A'}"
        )

        return (
            f"<b>[포트폴리오] {strategy}</b>\n"
            f"<i>{date_str}</i>\n\n"
            f"<b>요약</b>\n<blockquote>{summary}</blockquote>\n\n"
            f"<b>{section_title}</b>\n<blockquote>{body}</blockquote>\n\n"
            f"<b>성과</b>\n<blockquote>{metrics}</blockquote>\n\n"
            f"<i>현재 보유는 직전 리밸런싱 목표 비중으로 가정한 값입니다.</i>"
        )

    def _render_telegram(self, inp: ReportInput, seq: int) -> str:
        """Telegram HTML 포맷 — 표 대신 pre 블록, 헤더 대신 bold 사용."""
        sig = inp.signal
        m = sig.evidence_metrics

        def fmt_pct(v: float, sign: bool = True) -> str:
            if math.isnan(v):
                return "N/A"
            return f"{v:+.2%}" if sign else f"{v:.2%}"

        def fmt_f(v: float, decimals: int = 2) -> str:
            return f"{v:.{decimals}f}" if not math.isnan(v) else "N/A"

        signal_label = _SIGNAL_LABEL.get(sig.signal_type, sig.signal_type.value)
        sym = html_mod.escape(display_symbol(sig.symbol, inp.ticker_metadata))
        strategy = html_mod.escape(sig.strategy_display_name)
        rec = html_mod.escape(sig.position_recommendation)
        date_str = now_kst().strftime("%Y-%m-%d %H:%M KST") + f" #{seq}"
        mdd_str = f"-{m.mdd:.2%}" if not math.isnan(m.mdd) else "N/A"
        bm_note = f" ({html_mod.escape(m.benchmark_note)})" if m.benchmark_note else ""

        summary = (
            f"종목:  {sym}\n"
            f"날짜:  {sig.signal_date}\n"
            f"신호:  {signal_label}\n"
            f"전략:  {strategy}\n"
            f"점수:  {sig.score:.4f} / 1.0\n"
            f"권고:  {rec}"
        )

        metrics = (
            f"총수익률:  {fmt_pct(m.total_return)}\n"
            f"벤치마크:  {fmt_pct(m.benchmark_return)}{bm_note}\n"
            f"초과수익:  {fmt_pct(m.excess_return)}\n"
            f"MDD:      {mdd_str}\n"
            f"Sharpe:   {fmt_f(m.sharpe)}\n"
            f"Sortino:  {fmt_f(m.sortino)}\n"
            f"거래횟수:  {m.trade_count}\n"
            f"승률:     {fmt_pct(m.win_rate, sign=False)}\n"
            f"최근 6M:  {fmt_pct(m.recent_6m_return)}\n"
            f"최근 12M: {fmt_pct(m.recent_12m_return)}"
        )

        risk_section = ""
        if sig.risk_flags:
            flags = "\n".join(html_mod.escape(f) for f in sig.risk_flags)
            risk_section = f"\n\n<b>리스크 플래그</b>\n{flags}"

        return (
            f"<b>[{sym}] 퀀트 신호 리포트</b>\n"
            f"<i>{date_str}</i>\n\n"
            f"<b>신호 요약</b>\n<blockquote>{summary}</blockquote>\n\n"
            f"<b>백테스트 성과</b>\n<blockquote>{metrics}</blockquote>"
            f"{risk_section}"
        )
