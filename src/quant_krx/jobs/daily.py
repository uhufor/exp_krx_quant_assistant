from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from quant_krx.config.settings import Settings
from quant_krx.data.base import DataProvider
from quant_krx.llm import create_provider
from quant_krx.quant import (
    BollingerBandStrategy,
    MACDStrategy,
    MACrossoverStrategy,
    MomentumStrategy,
    RSIBreakoutStrategy,
    StrategyRunner,
)

_STRATEGY_REGISTRY = {
    "ma_crossover": lambda: MACrossoverStrategy(short_window=20, long_window=60),
    "rsi_breakout": lambda: RSIBreakoutStrategy(rsi_window=14, oversold=30.0, overbought=70.0),
    "bollinger_band": lambda: BollingerBandStrategy(window=20, num_std=2.0),
    "macd": lambda: MACDStrategy(fast=12, slow=26, signal=9),
    "momentum": lambda: MomentumStrategy(lookback_days=252, skip_days=21),
}
from quant_krx.reports import ReportARenderer, ReportBRenderer, ReportInput
from quant_krx.signals import SignalClassifier
from quant_krx.storage.db import Database
from quant_krx.storage.validation import DataValidator

if TYPE_CHECKING:
    from quant_krx.notify.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


@dataclass
class DailyJobResult:
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "running"          # running | ok | error
    symbol_count: int = 0
    signal_count: int = 0
    report_a_count: int = 0
    report_b_count: int = 0
    notification_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DailyJob:
    """
    일일 퀀트 파이프라인:
    fetch → validate → quant → signal → [report_a, report_b] → notify
    """

    def __init__(
        self,
        settings: Settings,
        db: Database,
        provider: DataProvider,
        notifier: TelegramNotifier | None = None,
    ):
        self._settings = settings
        self._db = db
        self._provider = provider
        self._notifier = notifier
        self._validator = DataValidator()
        self._runner = StrategyRunner()
        self._classifier = SignalClassifier(settings.evaluation.name)
        self._report_a = ReportARenderer()
        self._llm = create_provider(
            provider=settings.llm.provider,
            mock=settings.llm.mock,
            model=settings.llm.model,
        )
        self._report_b = ReportBRenderer(llm=self._llm)

    def run(
        self,
        dry_run: bool = False,
        as_of: date | None = None,
        enabled_strategies: list[str] | None = None,
    ) -> DailyJobResult:
        run_id = f"{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        result = DailyJobResult(run_id=run_id, started_at=datetime.utcnow())
        as_of = as_of or date.today()

        logger.info(f"[{run_id}] 일일 작업 시작 (dry_run={dry_run}, as_of={as_of})")
        self._db.log_event(run_id, "job_start", f"dry_run={dry_run}, as_of={as_of}")

        try:
            symbols = self._settings.load_watchlist()
            if not symbols:
                raise ValueError("Watchlist가 비어 있습니다.")
            result.symbol_count = len(symbols)

            # 1. 데이터 수집 + 검증
            end = as_of
            start = end - timedelta(days=365 * 5)  # 5년 히스토리

            ohlcv_map: dict[str, Any] = {}
            benchmark_df = None

            try:
                bench_data = self._provider.fetch_benchmark("KOSPI", start, end)
                benchmark_df = bench_data.df
            except Exception as e:
                logger.warning(f"벤치마크 수집 실패: {e}")

            for sym in symbols:
                try:
                    data = self._provider.fetch_ohlcv(sym, start, end)
                    issues = data.validate()
                    if not issues:
                        vr = self._validator.validate(sym, data.df, as_of=as_of)
                        if vr.ok:
                            for w in vr.warnings:
                                logger.warning(f"[{sym}] {w}")
                            self._db.upsert_ohlcv(
                                sym, data.df, data.meta.source_name, data.meta.fetched_at
                            )
                            ohlcv_map[sym] = data.df
                        else:
                            logger.warning(f"[{sym}] 검증 실패: {vr.issues}")
                            result.errors.append(f"{sym}: {vr.issues}")
                    else:
                        logger.warning(f"[{sym}] 데이터 오류: {issues}")
                        result.errors.append(f"{sym}: {issues}")
                except Exception as e:
                    logger.error(f"[{sym}] 수집 오류: {e}")
                    result.errors.append(f"{sym}: {e}")

            self._db.log_event(run_id, "fetch_done", f"{len(ohlcv_map)}/{len(symbols)} 종목 수집")

            try:
                ticker_metadata = self._provider.fetch_metadata(symbols)
            except Exception as e:
                logger.warning(f"종목 메타데이터 조회 실패: {e}")
                ticker_metadata = {}

            # 2. 퀀트 전략 실행
            enabled = enabled_strategies or self._settings.strategy.enabled
            strategies = [
                _STRATEGY_REGISTRY[name]()
                for name in enabled
                if name in _STRATEGY_REGISTRY
            ]
            if not strategies:
                raise ValueError(f"활성화된 전략이 없습니다. enabled={enabled}")
            backtest_results = self._runner.run_batch(
                strategies, ohlcv_map, benchmark_df, run_id=run_id
            )
            self._db.log_event(run_id, "quant_done", f"{len(backtest_results)} 전략 실행")

            # 3. 신호 생성 + 저장
            signals = self._classifier.classify_batch(backtest_results, signal_date=as_of)
            result.signal_count = len(signals)
            for sig in signals:
                self._db.insert_signal(sig.to_dict())
            self._db.log_event(run_id, "signal_done", f"{len(signals)} 신호")

            # 4. 리포트 생성 + 저장 (Report A/B 각각 개별 메시지로 발송)
            telegram_messages: list[str] = []
            msg_seq = 1
            for sig in signals:
                inp = ReportInput(signal=sig, ticker_metadata=ticker_metadata.get(sig.symbol, {}))
                ra = self._report_a.render(inp, seq=msg_seq)
                msg_seq += 1
                rb = self._report_b.render(inp, seq=msg_seq)
                msg_seq += 1
                self._db.insert_report(sig.id, "A", ra.content, run_id)
                self._db.insert_report(sig.id, "B", rb.content, run_id)
                result.report_a_count += 1
                result.report_b_count += 1
                telegram_messages.append(ra.telegram_content)
                telegram_messages.append(rb.telegram_content)

            self._db.log_event(
                run_id, "report_done",
                f"A={result.report_a_count}, B={result.report_b_count}",
            )

            # 5. 알림 발송 (Report A/B 각각 별도 메시지)
            if telegram_messages and not dry_run and self._notifier:
                for msg in telegram_messages:
                    nid = self._notifier.send(run_id, msg)
                    result.notification_ids.append(nid)
                logger.info(f"[{run_id}] Telegram 발송: {len(telegram_messages)}개 메시지")
            elif dry_run:
                logger.info(f"[{run_id}] dry_run: 알림 생략 ({len(signals)}개 신호 처리됨)")

            result.status = "ok"

        except Exception as e:
            result.status = "error"
            result.errors.append(str(e))
            logger.error(f"[{run_id}] 작업 오류: {e}")
            self._db.log_event(run_id, "job_error", str(e), level="ERROR")

        result.finished_at = datetime.utcnow()
        self._db.log_event(
            run_id, "job_done",
            f"status={result.status}, signals={result.signal_count}",
        )
        return result
