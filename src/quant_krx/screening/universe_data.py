from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd

from quant_krx.data.base import DataProvider, OHLCVData
from quant_krx.storage.db import Database

logger = logging.getLogger(__name__)

# I/O 바운드 네트워크 fetch만 병렬화한다(DuckDB 커넥션은 비-스레드세이프이므로 upsert는
# 항상 메인 스레드에서 순차 수행). 워커 수는 urllib3 기본 커넥션 풀 크기(10)를 넘지 않게
# 보수적으로 제한한다 — 풀 크기를 초과하면 매 요청마다 풀 밖에서 새 커넥션을 열고
# 버리게 되어("Connection pool is full" 경고) 대상 서버에 부하가 몰리기 쉽다.
_MAX_PARALLEL_FETCH_WORKERS = 8

# pykrx/FinanceDataReader의 내부 requests 호출은 timeout을 지정하지 않는다(각 라이브러리
# 소스에서 확인됨) — 서버가 응답을 주지 않으면 해당 워커 스레드가 영원히 블록되고,
# 이런 스레드가 누적되면 스레드풀 전체가 멈춘다. socket 기본 타임아웃을 fetch 구간에서만
# 지정해 블로킹 소켓 호출이 일정 시간 후 반드시 예외를 던지도록 강제한다(각 fetch 함수의
# 기존 try/except가 그 예외를 잡아 단위별로 격리하므로 스레드가 다음 작업을 계속 받는다).
_SOCKET_TIMEOUT_SECONDS = 30.0


def _existing_ohlcv_coverage(conn, symbols: list[str]) -> dict[str, tuple[date, date]]:
    """symbol별 ohlcv_daily 기존 커버리지(min/max date)를 조회한다."""
    if not symbols:
        return {}
    df = conn.execute(
        "SELECT symbol, MIN(date) AS min_date, MAX(date) AS max_date "
        "FROM ohlcv_daily WHERE symbol = ANY(?) GROUP BY symbol",
        [symbols],
    ).df()
    return {
        row["symbol"]: (pd.Timestamp(row["min_date"]).date(), pd.Timestamp(row["max_date"]).date())
        for _, row in df.iterrows()
    }


def _gap_ranges(
    existing: tuple[date, date] | None, start: date, end: date
) -> list[tuple[date, date]]:
    """요청 구간[start, end] 중 기존 커버리지 밖(이전/이후)만 반환한다.

    workspace/data_loading.py의 fundamental 전용 동명 함수와 동일한 패턴(경계 바깥만
    최소로 채운다)을 따르되, ohlcv_daily 테이블 대상으로 독립적으로 작성했다(다른
    테이블·호출 시그니처라 직접 재사용하지 않는다).
    """
    if existing is None:
        return [(start, end)]
    existing_min, existing_max = existing
    gaps: list[tuple[date, date]] = []
    if start < existing_min:
        gaps.append((start, min(existing_min - timedelta(days=1), end)))
    if end > existing_max:
        gaps.append((max(existing_max + timedelta(days=1), start), end))
    return gaps


def _with_socket_timeout(fn: Callable[[], None]) -> None:
    """fn 실행 구간에만 socket 기본 타임아웃을 걸고 종료 후 원래 값으로 복원한다."""
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(_SOCKET_TIMEOUT_SECONDS)
    try:
        fn()
    finally:
        socket.setdefaulttimeout(previous)


def _fetch_one_symbol(
    provider: DataProvider, symbol: str, gap_start: date, gap_end: date
) -> tuple[str, OHLCVData | None, Exception | None, float]:
    started = time.perf_counter()
    try:
        ohlcv_data = provider.fetch_ohlcv(symbol, gap_start, gap_end)
        return symbol, ohlcv_data, None, time.perf_counter() - started
    except Exception as e:  # noqa: BLE001 — 종목 단위 격리, 사유는 호출자에게 전달
        return symbol, None, e, time.perf_counter() - started


def _fetch_per_symbol(
    provider: DataProvider,
    fetch_jobs: list[tuple[str, date, date]],
    *,
    total: int,
    processed_start: int,
    on_symbol_error: Callable[[str, Exception], None] | None,
    on_progress: Callable[[int, int], None] | None,
) -> list[tuple[str, OHLCVData]]:
    """기존 종목 단위 순차/병렬 fetch 경로(provider가 날짜별 벌크 조회를 지원하지 않을 때
    쓰는 폴백 — FDR/Fixture 등 종목 단위 API만 있는 provider 대상)."""
    fetched: list[tuple[str, OHLCVData]] = []
    symbols_completed: set[str] = set()
    processed = processed_start
    total_elapsed = 0.0

    def _run() -> None:
        nonlocal processed, total_elapsed
        with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_FETCH_WORKERS) as executor:
            futures = [executor.submit(_fetch_one_symbol, provider, *job) for job in fetch_jobs]
            for future in as_completed(futures):
                symbol, ohlcv_data, error, elapsed = future.result()
                total_elapsed += elapsed
                if error is not None:
                    if on_symbol_error is not None:
                        on_symbol_error(symbol, error)
                elif ohlcv_data is not None and not ohlcv_data.df.empty:
                    fetched.append((symbol, ohlcv_data))

                if symbol not in symbols_completed:  # 종목당 gap 2개(양끝)여도 1회만 집계
                    symbols_completed.add(symbol)
                    processed += 1
                    if on_progress is not None:
                        on_progress(processed, total)
                    avg = total_elapsed / len(symbols_completed)
                    logger.info(
                        "[%d/%d] 종목 %s 처리 완료 (%.2f초, 평균 %.2f초/종목%s)",
                        processed, total, symbol, elapsed, avg,
                        "" if error is None else f", 실패: {error}",
                    )

    _with_socket_timeout(_run)
    return fetched


def _fetch_bulk_by_date(
    db: Database,
    provider: DataProvider,
    symbol_gaps: dict[str, list[tuple[date, date]]],
    *,
    market: str,
    total: int,
    processed_start: int,
    on_symbol_error: Callable[[str, Exception], None] | None,
    on_progress: Callable[[int, int], None] | None,
) -> None:
    """날짜별 벌크 조회 경로(provider가 fetch_ohlcv_bulk_by_date/list_trading_days를
    지원할 때만 사용 — 현재 PyKrxAdapter 전용). 종목별로 순차 호출(N종목 = N콜)하는
    대신 거래일별로 1콜씩 전 종목 데이터를 받아온다(거래일 수 << 종목 수이므로 총
    요청 수가 수십 배 줄어든다). 결과는 이 함수 내에서 바로 upsert까지 수행한다.
    """
    union_start = min(gap_start for gaps in symbol_gaps.values() for gap_start, _ in gaps)
    union_end = max(gap_end for gaps in symbol_gaps.values() for _, gap_end in gaps)

    trading_days: list[date] = provider.list_trading_days(union_start, union_end)

    # symbol_required_days는 조립 단계(파일 하단)에서 그대로 다시 읽어야 하므로 불변으로
    # 유지하고, 진행률 집계(어떤 종목이 "완료"됐는지)는 별도의 remaining 사본에서만 뺀다.
    symbol_required_days: dict[str, set[date]] = {
        symbol: {d for d in trading_days if any(gs <= d <= ge for gs, ge in gaps)}
        for symbol, gaps in symbol_gaps.items()
    }
    remaining_days_by_symbol: dict[str, set[date]] = {
        symbol: set(days) for symbol, days in symbol_required_days.items()
    }
    all_needed_days: set[date] = set().union(*symbol_required_days.values())

    logger.info(
        "스크리닝 OHLCV 벌크 조회 시작 — 거래일 %d일치 조회(종목별 순차 대비 요청 수 대폭 절감)",
        len(all_needed_days),
    )

    bulk_by_date: dict[date, pd.DataFrame] = {}
    processed = processed_start
    total_elapsed = 0.0
    dates_done = 0

    def _fetch_one_date(d: date) -> tuple[date, pd.DataFrame | None, Exception | None, float]:
        started = time.perf_counter()
        try:
            df = provider.fetch_ohlcv_bulk_by_date(d, market)
            return d, df, None, time.perf_counter() - started
        except Exception as e:  # noqa: BLE001 — 날짜 단위 격리
            return d, None, e, time.perf_counter() - started

    def _run() -> None:
        nonlocal processed, total_elapsed, dates_done
        with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_FETCH_WORKERS) as executor:
            futures = [executor.submit(_fetch_one_date, d) for d in all_needed_days]
            for future in as_completed(futures):
                d, df, error, elapsed = future.result()
                total_elapsed += elapsed
                dates_done += 1
                if error is not None:
                    logger.warning("거래일 %s 벌크 조회 실패, 건너뜀: %s", d, error)
                else:
                    bulk_by_date[d] = df

                avg = total_elapsed / dates_done
                logger.info(
                    "[거래일 %d/%d] %s 조회 완료 (%.2f초, 평균 %.2f초/거래일)",
                    dates_done, len(all_needed_days), d, elapsed, avg,
                )

                for symbol, remaining in remaining_days_by_symbol.items():
                    if d in remaining:
                        remaining.discard(d)
                        if not remaining:
                            processed += 1
                            if on_progress is not None:
                                on_progress(processed, total)

    _with_socket_timeout(_run)

    for symbol, required_days in symbol_required_days.items():
        rows = [
            bulk_by_date[d].loc[bulk_by_date[d]["symbol"] == symbol]
            for d in sorted(required_days)
            if d in bulk_by_date and (bulk_by_date[d]["symbol"] == symbol).any()
        ]
        if not rows:
            if on_symbol_error is not None:
                on_symbol_error(symbol, RuntimeError("벌크 조회 결과에 해당 종목 데이터 없음"))
            continue
        symbol_df = pd.concat(rows)[["date", "open", "high", "low", "close", "volume"]]
        symbol_df = symbol_df.reset_index(drop=True)
        db.upsert_ohlcv(symbol, symbol_df, provider.source_name, pd.Timestamp.utcnow())


def fetch_universe_ohlcv_cached(
    db: Database,
    provider: DataProvider,
    symbols: list[str],
    *,
    start: date,
    end: date,
    market: str = "KRX",
    use_cache: bool = True,
    on_symbol_error: Callable[[str, Exception], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """스캔 유니버스 종목의 OHLCV를 ohlcv_daily 캐시 우선으로 확보해 반환한다.

    종목별 기존 커버리지(min/max date)를 조회해, 요청 구간[start, end] 중 경계
    바깥(이전/이후)만 채워 upsert한다. 이미 확보된 구간은 재조회하지 않는다.
    use_cache=False면 커버리지 조회 없이 항상 전체 구간을 재조회한다.

    provider가 fetch_ohlcv_bulk_by_date/list_trading_days를 지원하면(현재 PyKrxAdapter만
    해당) 거래일별 벌크 조회 경로를 쓴다 — 종목 수(수천)가 아니라 거래일 수(수십~백여)만큼만
    네트워크 요청을 보내므로 요청 수가 수십 배 줄어든다. 미지원 provider(FDR/Fixture)는
    기존 종목별 병렬 fetch 경로로 폴백한다. 두 경로 모두 socket 타임아웃으로 응답 없는
    연결이 워커를 영원히 점유하지 못하게 막고, 실패는 종목(또는 거래일) 단위로 격리한다.

    on_progress(processed, total)는 종목 단위로 호출된다(total=len(symbols)).
    """
    with db.cursor() as conn:
        coverage = _existing_ohlcv_coverage(conn, symbols) if use_cache else {}

    symbol_gaps: dict[str, list[tuple[date, date]]] = {}
    for symbol in symbols:
        gaps = _gap_ranges(coverage.get(symbol), start, end) if use_cache else [(start, end)]
        gaps = [(gs, ge) for gs, ge in gaps if gs <= ge]
        if gaps:
            symbol_gaps[symbol] = gaps

    total = len(symbols)
    processed = total - len(symbol_gaps)  # 이미 캐시로 커버된 종목은 즉시 완료 처리
    if on_progress is not None:
        on_progress(processed, total)

    logger.info(
        "스크리닝 OHLCV 확보 시작 — 대상 %d종목, 캐시 히트 %d종목, fetch 필요 %d종목",
        total, processed, len(symbol_gaps),
    )

    run_started = time.perf_counter()
    supports_bulk = hasattr(provider, "fetch_ohlcv_bulk_by_date") and hasattr(
        provider, "list_trading_days"
    )
    if symbol_gaps and supports_bulk:
        _fetch_bulk_by_date(
            db, provider, symbol_gaps,
            market=market, total=total, processed_start=processed,
            on_symbol_error=on_symbol_error, on_progress=on_progress,
        )
    elif symbol_gaps:
        fetch_jobs = [
            (symbol, gs, ge) for symbol, gaps in symbol_gaps.items() for gs, ge in gaps
        ]
        fetched = _fetch_per_symbol(
            provider, fetch_jobs,
            total=total, processed_start=processed,
            on_symbol_error=on_symbol_error, on_progress=on_progress,
        )
        # DuckDB 커넥션은 비-스레드세이프 — upsert는 메인 스레드에서 순차 수행.
        for symbol, ohlcv_data in fetched:
            db.upsert_ohlcv(
                symbol, ohlcv_data.df, ohlcv_data.meta.source_name, ohlcv_data.meta.fetched_at
            )

    total_elapsed = time.perf_counter() - run_started
    logger.info("스크리닝 OHLCV 확보 완료 — %d종목, 총 %.1f초 소요", total, total_elapsed)

    with db.cursor() as conn:
        result: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            result[symbol] = conn.execute(
                "SELECT * FROM ohlcv_daily WHERE symbol=? AND date>=? AND date<=? ORDER BY date",
                [symbol, start, end],
            ).df()

    return result
