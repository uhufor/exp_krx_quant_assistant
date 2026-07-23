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


def test_run_reports_progress_up_to_universe_size(service) -> None:
    cond = _simple_condition("progress1")
    service.upsert_condition(cond, now=_NOW)

    calls: list[tuple[int, int]] = []
    service.run("progress1", on_progress=lambda done, total: calls.append((done, total)))

    assert calls  # 최소 1회는 호출됨
    assert all(total == 5 for _, total in calls)  # FixtureAdapter 5종목
    assert calls[-1][0] == 5  # 마지막 호출은 전체 완료
