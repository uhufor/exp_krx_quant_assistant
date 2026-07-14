from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from quant_krx.config.settings import Settings
from quant_krx.data.base import DataProvider
from quant_krx.data.fundamental_base import FundamentalProvider
from quant_krx.data.pykrx_fundamental import PyKrxFundamentalAdapter
from quant_krx.llm import create_provider
from quant_krx.reports import ReportARenderer, ReportBRenderer, ReportInput
from quant_krx.signals import SignalClassifier
from quant_krx.storage.db import Database
from quant_krx.storage.validation import DataValidator
from quant_krx.workspace.backtest import run_single_symbol_backtest
from quant_krx.workspace.data_loading import (
    build_factor_input_from_ohlcv,
    fetch_and_upsert_fundamentals,
)
from quant_krx.workspace.evaluation import strategy_required_data
from quant_krx.workspace.service import WorkspaceService
from quant_krx.workspace.templates import seed_builtin_strategies

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
    fetch → validate → evaluate/backtest(활성 선언형 전략) → signal → [report_a, report_b] → notify

    전략 실행 집합은 활성 선언형 전략 단일 원천이다(D3) — 코드형 전략 선택 기전은 없다.
    """

    def __init__(
        self,
        settings: Settings,
        db: Database,
        provider: DataProvider,
        notifier: TelegramNotifier | None = None,
        fundamental_provider: FundamentalProvider | None = None,
    ):
        self._settings = settings
        self._db = db
        self._provider = provider
        self._notifier = notifier
        self._fundamental_provider = fundamental_provider or PyKrxFundamentalAdapter()
        self._validator = DataValidator()
        self._workspace = WorkspaceService(db)
        self._classifier = SignalClassifier(settings.evaluation.name)
        self._report_a = ReportARenderer()
        llm_kwargs: dict[str, Any] = {
            "provider": settings.llm.provider,
            "mock": settings.llm.mock,
            "model": settings.llm.model,
        }
        # .env는 os.environ으로 export되지 않으므로 설정에서 읽은 키를 직접 전달
        if settings.llm.provider == "anthropic" and settings.llm.anthropic_api_key:
            llm_kwargs["api_key"] = settings.llm.anthropic_api_key
        self._llm = create_provider(**llm_kwargs)
        self._report_b = ReportBRenderer(llm=self._llm)

    def run(
        self, dry_run: bool = False, as_of: date | None = None, now: datetime | None = None
    ) -> DailyJobResult:
        run_id = f"{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        result = DailyJobResult(run_id=run_id, started_at=datetime.utcnow())
        as_of = as_of or date.today()
        now = now or datetime.utcnow()  # 시각 주입(INV-3) — 미지정 시에만 벽시계 폴백

        logger.info(f"[{run_id}] 일일 작업 시작 (dry_run={dry_run}, as_of={as_of})")
        self._db.log_event(run_id, "job_start", f"dry_run={dry_run}, as_of={as_of}")

        try:
            watchlist = self._settings.load_watchlist()
            if not watchlist:
                raise ValueError("Watchlist가 비어 있습니다.")

            # 0. 전환 시드(멱등) — Built-in 5종을 최초 1회 생성+활성화(FR-14a, D3 연속성)
            seed_builtin_strategies(self._workspace, now=now)

            # 1. 활성 실행 집합(FR-14) — id 정렬, 활성 0건은 명확 실패(조용한 no-op 금지)
            active_ids = self._workspace.list_active()
            if not active_ids:
                raise ValueError("활성 전략이 없습니다(활성 0건).")
            active_defns = [
                (sid, defn)
                for sid in active_ids
                if (defn := self._workspace.get_strategy(sid)) is not None
            ]

            # 2. universe 해석(D5, FR-15) — 수집 대상 = watchlist ∪ 활성 전략 universe 합집합
            extra_symbols: set[str] = set()
            for _, defn in active_defns:
                extra_symbols |= set(defn.universe.symbols)
            collect_symbols = sorted(set(watchlist) | extra_symbols)
            result.symbol_count = len(collect_symbols)

            # 3. 데이터 수집 + 검증
            end = as_of
            start = end - timedelta(days=365 * 5)  # 5년 히스토리

            ohlcv_map: dict[str, Any] = {}
            benchmark_df = None

            try:
                bench_data = self._provider.fetch_benchmark("KOSPI", start, end)
                benchmark_df = bench_data.df
            except Exception as e:
                logger.warning(f"벤치마크 수집 실패: {e}")

            for sym in collect_symbols:
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

            self._db.log_event(
                run_id, "fetch_done", f"{len(ohlcv_map)}/{len(collect_symbols)} 종목 수집"
            )

            try:
                ticker_metadata = self._provider.fetch_metadata(collect_symbols)
            except Exception as e:
                logger.warning(f"종목 메타데이터 조회 실패: {e}")
                ticker_metadata = {}

            # 4. 부가 데이터 자동 수집(FR-16) — required_data 합집합에 따라 조건부(ohlcv만이면 0회)
            required_union: set[str] = set()
            for _, defn in active_defns:
                required_union |= strategy_required_data(
                    defn, self._workspace.get_rule, self._workspace.get_formula
                )
            if required_union & {"valuation", "financials"}:
                fetch_and_upsert_fundamentals(
                    self._db, list(ohlcv_map.keys()), self._fundamental_provider,
                    start=start, end=end, as_of=as_of, kinds=frozenset(required_union),
                )

            # 5. 평가 + 백테스트(전략×종목 단위 실패 격리 — FR-17)
            backtest_results = []
            for sid, defn in active_defns:
                run_symbols = list(defn.universe.symbols) or watchlist
                for sym in run_symbols:
                    if sym not in ohlcv_map:
                        continue  # 수집 실패 종목은 이미 위에서 기록됨
                    try:
                        factor_input = build_factor_input_from_ohlcv(
                            self._db, sym, ohlcv_map[sym], start=start, end=end
                        )
                        bt_result = run_single_symbol_backtest(
                            defn, sym, factor_input,
                            fees=0.003, slippage=0.001, benchmark=benchmark_df,
                            resolve_formula=self._workspace.get_formula,
                            resolve_rule=self._workspace.get_rule,
                            start=start, end=end, run_id=run_id,
                        )
                        backtest_results.append(bt_result)
                    except Exception as e:
                        msg = f"{sid}×{sym}: {e}"
                        logger.error(msg)
                        result.errors.append(msg)
                        self._db.log_event(run_id, "strategy_symbol_error", msg, level="ERROR")

            self._db.log_event(run_id, "quant_done", f"{len(backtest_results)} 전략×종목 실행")

            # 6. 신호 생성 + 저장
            signals = self._classifier.classify_batch(backtest_results, signal_date=as_of)
            result.signal_count = len(signals)
            for sig in signals:
                self._db.insert_signal(sig.to_dict())
            self._db.log_event(run_id, "signal_done", f"{len(signals)} 신호")

            # 7. 리포트 생성 + 저장 (Report A/B 각각 개별 메시지로 발송, FR-18 다운스트림 동형)
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

            # 8. 알림 발송 (Report A/B 각각 별도 메시지)
            if telegram_messages and not dry_run and self._notifier:
                sent_count = 0
                for msg in telegram_messages:
                    try:
                        nid = self._notifier.send(run_id, msg)
                        result.notification_ids.append(nid)
                        sent_count += 1
                    except Exception as e:
                        # 실패 건은 outbox에 failed로 기록됨 — 나머지 메시지는 계속 발송
                        logger.error(f"[{run_id}] Telegram 발송 실패 (계속 진행): {e}")
                        result.errors.append(f"telegram: {e}")
                logger.info(
                    f"[{run_id}] Telegram 발송: {sent_count}/{len(telegram_messages)}개 메시지"
                )
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
