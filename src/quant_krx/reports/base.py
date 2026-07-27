from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quant_krx.signals.classifier import PORTFOLIO_SYMBOL, Signal
from quant_krx.signals.rebalance import RebalancePlan

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


@dataclass
class ReportInput:
    signal: Signal
    # 허용 컨텍스트 (theme_labels/regime_summary는 Report B 전용, ticker_metadata의
    # name은 Report A/B 공통으로 종목명 표시에 사용)
    theme_labels: list[str] = field(default_factory=list)
    ticker_metadata: dict[str, Any] = field(default_factory=dict)
    regime_summary: str = ""  # 시스템이 생성한 레짐 요약
    # 포트폴리오 전략(R05)일 때만 채워진다. 있으면 렌더러가 계좌 단위 포맷으로 분기한다.
    rebalance_plan: RebalancePlan | None = None
    # 포트폴리오 구성 종목의 이름 표시용 {symbol: {"name": ...}}.
    symbol_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RenderedReport:
    signal_id: str       # 반드시 signal.id와 일치
    report_type: str     # "A" | "B"
    content: str         # Markdown 텍스트 (DB 저장, CLI 표시용)
    telegram_content: str = field(default="")  # Telegram HTML (발송용)
    created_at: datetime = field(default_factory=now_kst)
    llm_used: bool = False


def display_symbol(symbol: str, ticker_metadata: dict[str, Any]) -> str:
    """'380550 - 뉴로핏' 형식. name이 없으면 종목코드만 반환.

    포트폴리오 신호(R05)는 symbol이 종목이 아니라 계좌를 뜻하는 의사 키이므로 그대로
    노출하지 않고 한국어 라벨로 바꾼다.
    """
    if symbol == PORTFOLIO_SYMBOL:
        return "포트폴리오"
    name = ticker_metadata.get("name", "")
    return f"{symbol} - {name}" if name else symbol
