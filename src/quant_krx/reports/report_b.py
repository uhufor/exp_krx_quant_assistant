from __future__ import annotations

import html as html_mod
import math
import re

from quant_krx.llm.base import LLMProvider
from quant_krx.signals.classifier import SignalType

from .base import RenderedReport, ReportInput, display_symbol, now_kst

_SIGNAL_LABEL = {
    SignalType.BUY: "🟢 매수",
    SignalType.SELL: "🔴 매도",
    SignalType.HOLD: "🟡 보유",
    SignalType.WATCH: "🟠 관망",
    SignalType.NO_SIGNAL: "⚪ 신호없음",
}


def _convert_blockquotes(text: str) -> str:
    """이스케이프된 Markdown '&gt; ' 인용구 줄을 Telegram <blockquote>로 병합 변환."""
    lines = text.split("\n")
    result: list[str] = []
    quote_buf: list[str] = []

    def flush() -> None:
        if quote_buf:
            joined = "\n".join(quote_buf)
            result.append(f"<blockquote>{joined}</blockquote>")
            quote_buf.clear()

    for line in lines:
        if line.startswith("&gt; "):
            quote_buf.append(line[len("&gt; "):])
        elif line == "&gt;":
            quote_buf.append("")
        else:
            flush()
            result.append(line)
    flush()
    return "\n".join(result)


def _md_to_html(text: str) -> str:
    """LLM Markdown 출력을 Telegram HTML로 변환."""
    out = html_mod.escape(text)
    out = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", out, flags=re.MULTILINE)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out, flags=re.DOTALL)
    out = re.sub(r"\*(.+?)\*", r"<i>\1</i>", out, flags=re.DOTALL)
    out = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", out)
    out = _convert_blockquotes(out)
    return out


class ReportBRenderer:
    """
    Report B: 동일 Signal + 허용 컨텍스트 + LLM 보조 해석.
    - 동일 signal_id 참조 (Report A와 동일)
    - LLM이 없으면 Report A 내용 + [LLM 없음] 메시지로 폴백
    - LLM 출력에 fact / inference / recommendation 섹션 강제
    """

    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm

    def render(self, inp: ReportInput, seq: int = 1) -> RenderedReport:
        sig = inp.signal
        m = sig.evidence_metrics

        def fmt_pct(v: float) -> str:
            return f"{v:.2%}" if not math.isnan(v) else "N/A"

        sharpe_str = f"{m.sharpe:.2f}" if not math.isnan(m.sharpe) else "N/A"

        prompt = self._build_prompt(inp)

        if self.llm is None:
            llm_raw = (
                "> ⚠️ LLM 제공자가 설정되지 않았습니다. "
                "LLM 해석 없이 퀀트 팩트만 표시합니다."
            )
            llm_used = False
        else:
            try:
                llm_raw = self.llm.complete(prompt)
                llm_used = True
            except Exception as e:
                llm_raw = f"> ⚠️ LLM 호출 실패: {e}\n> 퀀트 팩트만 표시합니다."
                llm_used = False

        context_section = ""
        if inp.theme_labels:
            context_section += f"**테마**: {', '.join(inp.theme_labels)}\n"
        if inp.regime_summary:
            context_section += f"**레짐 요약**: {inp.regime_summary}\n"

        sym_display = display_symbol(sig.symbol, inp.ticker_metadata)

        content = f"""# [Report B] {sym_display} 퀀트+컨텍스트 신호 리포트
> **리포트 유형**: B (퀀트 + LLM 보조)
> **신호 ID**: `{sig.id}`  ← Report A와 동일한 신호 참조
> **실행 ID**: `{sig.run_id}`
> **생성 일시**: {now_kst().strftime('%Y-%m-%d %H:%M KST')}
> **LLM 사용**: {'예' if llm_used else '아니오'}

---

## 퀀트 신호 요약 (Report A와 동일 신호)

| 항목 | 값 |
|------|----|
| 종목 | {sym_display} |
| 신호 | **{sig.signal_type.value.upper()}** |
| 점수 | {sig.score:.4f} |
| MDD | {fmt_pct(m.mdd)} |
| Sharpe | {sharpe_str} |
| 리스크 플래그 | {', '.join(sig.risk_flags) if sig.risk_flags else '없음'} |

---

## 허용 컨텍스트

{context_section if context_section else '_컨텍스트 없음_'}

---

## LLM 보조 해석

{llm_raw}
"""
        return RenderedReport(
            signal_id=sig.id,
            report_type="B",
            content=content.strip(),
            telegram_content=self._render_telegram(sig, m, llm_raw, llm_used, inp, seq),
            llm_used=llm_used,
        )

    def _render_telegram(
        self, sig, m, llm_raw: str, llm_used: bool, inp: ReportInput, seq: int
    ) -> str:
        """Telegram HTML 포맷 — LLM 출력도 HTML로 변환."""
        def fmt_pct(v: float) -> str:
            if math.isnan(v):
                return "N/A"
            return f"{v:+.2%}"

        def fmt_f(v: float, decimals: int = 2) -> str:
            return f"{v:.{decimals}f}" if not math.isnan(v) else "N/A"

        signal_label = _SIGNAL_LABEL.get(sig.signal_type, sig.signal_type.value)
        sym = html_mod.escape(display_symbol(sig.symbol, inp.ticker_metadata))
        strategy = html_mod.escape(sig.strategy_display_name)
        date_str = now_kst().strftime("%Y-%m-%d %H:%M KST") + f" #{seq}"
        mdd_str = f"-{m.mdd:.2%}" if not math.isnan(m.mdd) else "N/A"
        risk_str = html_mod.escape(", ".join(sig.risk_flags)) if sig.risk_flags else "없음"

        summary = (
            f"전략:   {strategy}\n"
            f"신호:   {signal_label}\n"
            f"점수:   {sig.score:.4f}\n"
            f"MDD:   {mdd_str}\n"
            f"Sharpe: {fmt_f(m.sharpe)}\n"
            f"리스크: {risk_str}"
        )

        llm_html = _md_to_html(llm_raw)

        return (
            f"<b>[{sym}] 퀀트+LLM 리포트</b>\n"
            f"<i>{date_str}</i>\n\n"
            f"<b>신호 요약</b>\n<blockquote>{summary}</blockquote>\n\n"
            f"<b>LLM 해석</b>\n{llm_html}"
        )

    @staticmethod
    def _subject_lines(inp: ReportInput) -> str:
        """분석 대상 서술 — 종목 신호와 포트폴리오 신호(R05)는 대상 자체가 다르다.

        포트폴리오에 `- 종목: __portfolio__`를 그대로 넣으면 LLM이 존재하지 않는 종목을
        분석하려 들므로, 구성 종목과 매매 지시를 팩트로 제시한다.
        """
        plan = inp.rebalance_plan
        if plan is None:
            return f"- 종목: {inp.signal.symbol}"

        holdings = ", ".join(plan.target_symbols) or "없음"
        lines = [
            "- 분석 대상: 포트폴리오(개별 종목이 아닌 계좌 전체)",
            f"- 목표 보유 종목: {holdings}",
            f"- 리밸런싱 지시: {plan.summary()}",
            f"- 오늘 리밸런싱일 여부: {'예' if plan.is_rebalance_day else '아니오'}",
        ]
        return "\n".join(lines)

    def _build_prompt(self, inp: ReportInput) -> str:
        sig = inp.signal
        m = sig.evidence_metrics

        def fmt_pct(v: float) -> str:
            return f"{v:.2%}" if not math.isnan(v) else "N/A"

        context_lines = []
        if inp.theme_labels:
            context_lines.append(f"테마: {', '.join(inp.theme_labels)}")
        if inp.ticker_metadata:
            name = inp.ticker_metadata.get("name", "")
            if name:
                context_lines.append(f"종목명: {name}")
        if inp.regime_summary:
            context_lines.append(f"레짐: {inp.regime_summary}")
        context_str = "\n".join(context_lines) if context_lines else "없음"
        sharpe_str = f"{m.sharpe:.2f}" if not math.isnan(m.sharpe) else "N/A"

        intro = (
            "당신은 한국 주식 시장 분석가입니다. "
            "아래 퀀트 신호와 컨텍스트를 바탕으로 분석 리포트를 작성하세요."
        )
        return f"""{intro}

## 퀀트 신호 (변경 불가 팩트)
{self._subject_lines(inp)}
- 신호: {sig.signal_type.value}
- 점수: {sig.score:.4f}
- 전략: {sig.strategy_display_name}
- 총수익률: {fmt_pct(m.total_return)}
- 초과수익률: {fmt_pct(m.excess_return)}{f' ({m.benchmark_note})' if m.benchmark_note else ''}
- MDD: {fmt_pct(m.mdd)}
- Sharpe: {sharpe_str}
- 최근6M: {fmt_pct(m.recent_6m_return)}
- 리스크 플래그: {', '.join(sig.risk_flags) if sig.risk_flags else '없음'}

## 허용 컨텍스트
{context_str}

## 작성 지침
다음 3개 섹션으로 구분하여 작성하세요:

### 팩트 (Fact)
퀀트 신호에서 직접 도출한 객관적 사실만 기술하세요.

### 추론 (Inference)
팩트와 컨텍스트를 바탕으로 한 분석적 추론을 기술하세요. 불확실성을 명시하세요.

### 권고 (Recommendation)
투자 결정에 참고할 수 있는 관점을 제시하세요. "투자 권유가 아님"을 명시하세요.

퀀트 신호를 무시하거나 덮어쓰지 마세요. 리스크 플래그가 있다면 반드시 언급하세요."""
