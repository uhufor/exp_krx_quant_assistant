from __future__ import annotations

import inspect
from datetime import datetime

import pytest

from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.screening import service as service_mod
from quant_krx.screening import universe as universe_mod
from quant_krx.screening.definition import (
    Composition,
    ConstantOperand,
    FactorOperand,
    FormulaOperand,
    Predicate,
    RankPredicate,
    ScanUniverse,
    ScreeningCondition,
)
from quant_krx.screening.service import ScreeningService, ValidationResult
from quant_krx.storage.db import Database

_NOW = datetime(2024, 12, 18, 9, 0, 0)


@pytest.fixture
def service(tmp_path):
    db = Database(path=tmp_path / "screening.duckdb")
    db.connect()
    try:
        yield ScreeningService(db, FixtureAdapter())
    finally:
        db.close()


def _simple_condition(cond_id: str = "c1") -> ScreeningCondition:
    return ScreeningCondition(
        id=cond_id,
        name="종가 20만 초과",
        version="1",
        universe=ScanUniverse(market="KRX", exclusion_filters=frozenset()),
        root=Predicate(
            left=FactorOperand(factor_id="price", column="close"),
            operator=">",
            right=ConstantOperand(value=200000),
        ),
    )


# --- CRUD 왕복 -------------------------------------------------------------------


def test_crud_roundtrip(service) -> None:
    cond = _simple_condition()
    assert service.get_condition("c1") is None
    assert service.list_conditions() == ()

    service.upsert_condition(cond, now=_NOW)
    loaded = service.get_condition("c1")
    assert loaded == cond
    assert service.list_conditions() == (cond,)

    edited = ScreeningCondition(
        id="c1", name="이름 변경", version="2", universe=cond.universe, root=cond.root
    )
    service.upsert_condition(edited, now=_NOW)
    reloaded = service.get_condition("c1")
    assert reloaded.name == "이름 변경"
    assert reloaded.version == "2"
    assert len(service.list_conditions()) == 1  # upsert(멱등, 신규 행 아님)

    service.delete_condition("c1")
    assert service.get_condition("c1") is None
    assert service.list_conditions() == ()


# --- 검증 ------------------------------------------------------------------------


def test_validate_condition_ok(service) -> None:
    result = service.validate_condition(_simple_condition())
    assert isinstance(result, ValidationResult)
    assert result.ok
    assert result.errors == ()


def test_validate_condition_unknown_factor(service) -> None:
    cond = ScreeningCondition(
        id="bad",
        name="미지 팩터",
        version="1",
        universe=ScanUniverse(),
        root=Predicate(
            left=FactorOperand(factor_id="does_not_exist", column="value"),
            operator=">",
            right=ConstantOperand(value=0),
        ),
    )
    result = service.validate_condition(cond)
    assert not result.ok
    assert any("does_not_exist" in e for e in result.errors)


def test_validate_condition_rejects_formula_operand(service) -> None:
    cond = ScreeningCondition(
        id="f",
        name="formula 미지원",
        version="1",
        universe=ScanUniverse(),
        root=Predicate(
            left=FormulaOperand(formula_id="custom"),
            operator=">",
            right=ConstantOperand(value=0),
        ),
    )
    result = service.validate_condition(cond)
    assert not result.ok
    assert any("FormulaOperand" in e for e in result.errors)


def test_validate_condition_rank_predicate_bad_column(service) -> None:
    cond = ScreeningCondition(
        id="r",
        name="잘못된 순위 컬럼",
        version="1",
        universe=ScanUniverse(),
        root=RankPredicate(
            factor_id="momentum", column="not_a_snapshot_col", rank_metric="desc", top_n=5
        ),
    )
    result = service.validate_condition(cond)
    assert not result.ok
    assert any("not_a_snapshot_col" in e for e in result.errors)


def test_validate_condition_rank_predicate_unknown_factor(service) -> None:
    cond = ScreeningCondition(
        id="rank_bad_factor",
        name="미지 팩터 참조 랭킹",
        version="1",
        universe=ScanUniverse(),
        root=RankPredicate(
            factor_id="does_not_exist", column="trading_value", rank_metric="desc", top_n=5
        ),
    )
    result = service.validate_condition(cond)
    assert not result.ok
    assert any("does_not_exist" in e for e in result.errors)


def test_validate_condition_walks_nested_tree(service) -> None:
    cond = ScreeningCondition(
        id="nested",
        name="중첩",
        version="1",
        universe=ScanUniverse(),
        root=Composition(
            op="AND",
            operands=(
                Predicate(
                    left=FactorOperand(factor_id="price", column="close"),
                    operator=">",
                    right=ConstantOperand(value=0),
                ),
                RankPredicate(
                    factor_id="trading_value", column="trading_value",
                    rank_metric="desc", top_n=2,
                ),
            ),
        ),
    )
    assert service.validate_condition(cond).ok


# --- run() 미존재 조건 -----------------------------------------------------------


def test_run_missing_condition_raises(service) -> None:
    from quant_krx.screening.errors import ScreeningError

    with pytest.raises(ScreeningError, match="찾을 수 없습니다"):
        service.run("nope")


def test_run_escalates_when_all_symbol_evaluations_fail(service) -> None:
    """평가 코드/설정 오류(존재하지 않는 팩터 컬럼 참조)가 전 종목에서 동일하게 발생하면
    조용히 빈 결과를 반환하지 않고 ScreeningError로 승격한다(I1 회귀) — 종목별 데이터
    이슈(빈 유니버스 등)와 구분되는 시스템적 실패를 사용자가 인지할 수 있어야 한다."""
    from datetime import date

    from quant_krx.screening.errors import ScreeningError

    cond = ScreeningCondition(
        id="bad_column_run",
        name="잘못된 컬럼 참조",
        version="1",
        universe=ScanUniverse(market="KRX", exclusion_filters=frozenset()),
        root=Predicate(
            left=FactorOperand(factor_id="price", column="does_not_exist_column"),
            operator=">",
            right=ConstantOperand(value=0),
        ),
    )
    service.upsert_condition(cond, now=_NOW)

    with pytest.raises(ScreeningError, match="모두 실패"):
        service.run("bad_column_run", as_of=date(2024, 12, 18))


# --- watchlist 비관여 (config/watchlist.yaml이 스크리닝 경로에 관여하지 않음) -----


def test_screening_source_does_not_reference_watchlist() -> None:
    """스크리닝 실행 경로(service/universe)는 watchlist를 읽지 않는다(설계 확정)."""
    assert "watchlist" not in inspect.getsource(service_mod).lower()
    assert "watchlist" not in inspect.getsource(universe_mod).lower()


# --- count_universe / on_progress (실행 전 대상 종목수 표시, 진행률) ------------------


def test_count_universe_returns_universe_size_without_running(service) -> None:
    cond = _simple_condition("count1")
    service.upsert_condition(cond, now=_NOW)
    assert service.count_universe("count1") == 5  # FixtureAdapter 5종목


def test_count_universe_missing_condition_raises(service) -> None:
    from quant_krx.screening.errors import ScreeningError

    with pytest.raises(ScreeningError, match="찾을 수 없습니다"):
        service.count_universe("nope")


# --- _compute_lookback_start (I2: 거래일 캘린더 기반 lookback 정밀화) -----------------


class _TradingDaysStubProvider:
    """list_trading_days만 구현한 최소 스텁(PyKrx류 provider 흉내, I2 검증 전용)."""

    def __init__(self, trading_days: list) -> None:
        self._trading_days = trading_days

    def list_trading_days(self, start, end) -> list:
        return [d for d in self._trading_days if start <= d <= end]


def test_compute_lookback_start_zero_bars_returns_as_of() -> None:
    from datetime import date

    from quant_krx.screening.service import _compute_lookback_start

    provider = _TradingDaysStubProvider([])
    as_of = date(2024, 12, 18)
    assert _compute_lookback_start(provider, as_of, 0) == as_of


def test_compute_lookback_start_uses_trading_day_calendar_when_supported() -> None:
    from datetime import date, timedelta

    from quant_krx.screening.service import _compute_lookback_start

    as_of = date(2024, 12, 18)
    trading_days = []
    d = as_of
    while len(trading_days) < 25:
        if d.weekday() < 5:  # 평일만(주말 제외)
            trading_days.append(d)
        d -= timedelta(days=1)
    provider = _TradingDaysStubProvider(trading_days)

    start = _compute_lookback_start(provider, as_of, lookback_bars=5)
    expected = sorted(trading_days)[-6]  # as_of 포함 최근 6거래일(5+1) 중 가장 이른 날짜
    assert start == expected


def test_compute_lookback_start_expands_search_window_on_holiday_cluster() -> None:
    """1차 조회 구간에 거래일이 부족하면(공휴일 군집) 구간을 넓혀 재시도한다(I2 회귀) —
    고정 배수(_CALENDAR_DAY_MARGIN)만 쓰면 연휴 구간에서 warm-up이 부족해질 수 있었다."""
    from datetime import date, timedelta

    from quant_krx.screening.service import _compute_lookback_start

    as_of = date(2024, 12, 18)
    lookback_bars = 10

    # 1차 시도 구간(15일)에는 거래일이 없도록 2024-12-03~12-17을 통째로 공휴일로
    # 비우고(설/추석 연휴 흉내), 그보다 이전(2024-11-18~12-02, 평일 11일)에만 거래일을
    # 둔다 — 1차 시도는 as_of 하루만 잡혀 부족하고, 2차(확장) 시도에서 충분해진다.
    trading_days: list[date] = []
    d = date(2024, 11, 18)
    while d <= date(2024, 12, 2):
        if d.weekday() < 5:
            trading_days.append(d)
        d += timedelta(days=1)
    trading_days.append(as_of)
    provider = _TradingDaysStubProvider(trading_days)

    first_window_days = provider.list_trading_days(
        as_of - timedelta(days=int(lookback_bars * 1.5)), as_of
    )
    assert len(first_window_days) < lookback_bars + 1  # 1차 시도는 부족해야 테스트가 유효

    start = _compute_lookback_start(provider, as_of, lookback_bars)
    resolved_days = provider.list_trading_days(start, as_of)
    assert len(resolved_days) >= lookback_bars + 1


def test_compute_lookback_start_falls_back_to_margin_when_unsupported(service) -> None:
    """list_trading_days 미지원 provider(FDR/Fixture)는 기존 배수 추정으로 폴백한다."""
    from datetime import date, timedelta

    from quant_krx.data.fixture_adapter import FixtureAdapter
    from quant_krx.screening.service import _CALENDAR_DAY_MARGIN, _compute_lookback_start

    provider = FixtureAdapter()
    assert not hasattr(provider, "list_trading_days")
    as_of = date(2024, 12, 18)
    lookback_bars = 10
    expected = as_of - timedelta(days=int(lookback_bars * _CALENDAR_DAY_MARGIN))
    assert _compute_lookback_start(provider, as_of, lookback_bars) == expected


def test_run_reports_progress_up_to_universe_size(service) -> None:
    cond = _simple_condition("progress1")
    service.upsert_condition(cond, now=_NOW)

    calls: list[tuple[int, int]] = []
    service.run("progress1", on_progress=lambda done, total: calls.append((done, total)))

    assert calls  # 최소 1회는 호출됨
    assert all(total == 5 for _, total in calls)  # FixtureAdapter 5종목
    assert calls[-1][0] == 5  # 마지막 호출은 전체 완료
