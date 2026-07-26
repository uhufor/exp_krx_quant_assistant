from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from quant_krx.data.fixture_adapter import FIXTURE_PATH, FixtureAdapter
from quant_krx.screening.definition import (
    ConstantOperand,
    FactorOperand,
    Predicate,
    RankPredicate,
    ScanUniverse,
    ScreeningCondition,
)
from quant_krx.screening.service import ScreeningService
from quant_krx.storage.db import Database

_NOW = datetime(2024, 12, 18, 9, 0, 0)
_AS_OF = date(2024, 12, 18)  # 픽스처 마지막 거래일


@pytest.fixture
def service(tmp_path):
    db = Database(path=tmp_path / "screening.duckdb")
    db.connect()
    try:
        yield ScreeningService(db, FixtureAdapter())
    finally:
        db.close()


def _last_bar_snapshot() -> pd.DataFrame:
    """픽스처 마지막 거래일의 종가/거래대금 — 기대값 계산의 진실 원천."""
    df = pd.read_csv(FIXTURE_PATH, dtype={"symbol": str}, parse_dates=["date"])
    df["symbol"] = df["symbol"].str.zfill(6)
    snap = df[df["date"] == pd.Timestamp(_AS_OF)][["symbol", "close", "volume"]].copy()
    snap["trading_value"] = snap["close"] * snap["volume"]
    return snap


def test_run_simple_price_predicate(service) -> None:
    """종가 > 200000 조건 → 픽스처에서 직접 계산한 통과 종목과 일치한다."""
    snap = _last_bar_snapshot()
    expected = sorted(snap.loc[snap["close"] > 200000, "symbol"])

    cond = ScreeningCondition(
        id="price_gt",
        name="종가 20만 초과",
        version="1",
        universe=ScanUniverse(market="KRX", exclusion_filters=frozenset()),
        root=Predicate(
            left=FactorOperand(factor_id="price", column="close"),
            operator=">",
            right=ConstantOperand(value=200000),
        ),
    )
    service.upsert_condition(cond, now=_NOW)

    result = service.run("price_gt", as_of=_AS_OF)
    passed = sorted(s for s, *_ in result)
    assert passed == expected
    assert expected  # 픽스처상 최소 1종목은 통과해야 함(테스트 유효성)
    # 반환은 (symbol, name, market) 튜플 형태 — FixtureAdapter는 5종목 모두 KOSPI 고정.
    assert all(isinstance(item, tuple) and len(item) == 3 for item in result)
    assert all(market == "KOSPI" for _, _, market in result)


def test_run_rank_predicate_top_n(service) -> None:
    """거래대금 Top-2 조건 → 스냅샷에서 직접 계산한 상위 2종목과 일치한다."""
    snap = _last_bar_snapshot()
    expected = sorted(snap.sort_values("trading_value", ascending=False).head(2)["symbol"])

    cond = ScreeningCondition(
        id="tv_top2",
        name="거래대금 Top-2",
        version="1",
        universe=ScanUniverse(market="KRX", exclusion_filters=frozenset()),
        root=RankPredicate(
            factor_id="trading_value",
            column="trading_value",
            rank_metric="desc",
            top_n=2,
        ),
    )
    service.upsert_condition(cond, now=_NOW)

    result = service.run("tv_top2", as_of=_AS_OF)
    passed = sorted(s for s, *_ in result)
    assert passed == expected
    assert len(expected) == 2


def test_run_rank_only_condition_skips_ohlcv_fetch(service, monkeypatch) -> None:
    """순수 RankPredicate 조건은 OHLCV를 전혀 조회하지 않고 스냅샷만으로 평가된다(I4 회귀).

    fetch_universe_ohlcv_cached가 호출되면 즉시 실패시켜, OHLCV 결측/일시 조회 실패가
    순수 순위 조건 결과에 영향을 줄 수 없음을 증명한다(이전에는 OHLCV가 비어있으면
    순위상 통과해야 할 종목도 조용히 skip됐다).
    """
    from quant_krx.screening import service as service_mod

    def _boom(*args, **kwargs):
        raise AssertionError("순수 RankPredicate 조건은 OHLCV를 조회하면 안 됩니다")

    monkeypatch.setattr(service_mod, "fetch_universe_ohlcv_cached", _boom)

    snap = _last_bar_snapshot()
    expected = sorted(snap.sort_values("trading_value", ascending=False).head(2)["symbol"])

    cond = ScreeningCondition(
        id="tv_top2_no_fetch",
        name="거래대금 Top-2(OHLCV 미조회 검증)",
        version="1",
        universe=ScanUniverse(market="KRX", exclusion_filters=frozenset()),
        root=RankPredicate(
            factor_id="trading_value",
            column="trading_value",
            rank_metric="desc",
            top_n=2,
        ),
    )
    service.upsert_condition(cond, now=_NOW)

    result = service.run("tv_top2_no_fetch", as_of=_AS_OF)
    passed = sorted(s for s, *_ in result)
    assert passed == expected


def test_run_does_not_read_watchlist(service, monkeypatch) -> None:
    """run()은 config/watchlist.yaml을 어떤 경로로도 읽지 않는다."""
    from quant_krx.config.settings import Settings

    def _boom(self):  # pragma: no cover - 호출되면 실패
        raise AssertionError("run()이 watchlist를 읽어서는 안 됩니다")

    monkeypatch.setattr(Settings, "load_watchlist", _boom)

    cond = ScreeningCondition(
        id="w",
        name="watchlist 무관",
        version="1",
        universe=ScanUniverse(market="KRX", exclusion_filters=frozenset()),
        root=Predicate(
            left=FactorOperand(factor_id="price", column="close"),
            operator=">",
            right=ConstantOperand(value=0),
        ),
    )
    service.upsert_condition(cond, now=_NOW)

    result = service.run("w", as_of=_AS_OF)
    # 종가 > 0은 전 종목 통과 → 유니버스 전체(= list_symbols)와 동일
    assert sorted(s for s, *_ in result) == sorted(FixtureAdapter().list_symbols())
