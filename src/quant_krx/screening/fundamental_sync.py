from __future__ import annotations

from datetime import date, datetime

from quant_krx.data.coverage import (
    date_range_gaps,
    existing_financials_periods,
    existing_valuation_coverage,
    latest_financials_period,
)
from quant_krx.data.coverage import (
    is_financials_stale as _is_stale,
)
from quant_krx.data.upsert import upsert_fundamental
from quant_krx.storage.db import Database


def sync_universe_fundamentals(
    db: Database,
    symbols: list[str],
    *,
    as_of: date,
    needs_valuation: bool,
    needs_financials: bool,
) -> None:
    """스크리닝 실행 직전 유니버스 펀더멘털을 신선도 체크 후 부족분만 벌크 동기화한다(TRD-R04 §3).

    갱신 대상이 0종목이면 provider를 아예 만들지 않는다(바이패스). 종목 단위/provider 단위
    실패는 조용히 건너뛰고 계속한다 — 하나의 corp_code 미해결·API 오류·자격증명 미설정이
    스크리닝 전체를 막지 않는다(해당 종목/factor는 NaN으로 자연 결측 처리, 기존 원칙과 동일).
    """
    if needs_valuation:
        _sync_valuation(db, symbols, as_of=as_of)
    if needs_financials:
        _sync_financials(db, symbols, as_of=as_of)


def _sync_valuation(db: Database, symbols: list[str], *, as_of: date) -> None:
    with db.cursor() as conn:
        coverage = existing_valuation_coverage(conn, symbols)
    stale_symbols = [s for s in symbols if date_range_gaps(coverage.get(s), as_of, as_of)]
    if not stale_symbols:
        return

    from quant_krx.data.pykrx_fundamental import PyKrxFundamentalAdapter

    provider = PyKrxFundamentalAdapter()
    try:
        frame = provider.fetch_valuation(stale_symbols, as_of, as_of)
    except Exception:  # noqa: BLE001 — 밸류에이션 동기화 실패는 스크리닝 자체를 막지 않음
        return
    if frame.empty:
        return
    frame = frame.assign(source=provider.source_name, fetched_at=datetime.utcnow())
    with db.cursor() as conn:
        upsert_fundamental(conn, "fundamental_daily", frame, as_of=as_of)


def _sync_financials(db: Database, symbols: list[str], *, as_of: date) -> None:
    with db.cursor() as conn:
        latest = latest_financials_period(conn, symbols)
    stale_symbols = [s for s in symbols if _is_stale(latest.get(s), as_of)]
    if not stale_symbols:
        return

    with db.cursor() as conn:
        skip_periods = existing_financials_periods(conn, stale_symbols)

    from quant_krx.data.dart_fundamental import DartFundamentalAdapter

    try:
        provider = DartFundamentalAdapter()
    except RuntimeError:  # DART_API_KEY 미설정 — 재무 순위만 스킵, 나머지 조건은 계속 진행
        return
    try:
        frame = provider.fetch_latest_financials(stale_symbols, as_of, skip_periods=skip_periods)
    except Exception:  # noqa: BLE001 — 재무 동기화 실패는 스크리닝 자체를 막지 않음
        return
    finally:
        provider.close()

    if frame.empty:
        return
    frame = frame.assign(source=provider.source_name, fetched_at=datetime.utcnow())
    with db.cursor() as conn:
        upsert_fundamental(conn, "financial_statements", frame, as_of=as_of)
