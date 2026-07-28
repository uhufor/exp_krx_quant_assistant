from __future__ import annotations

from datetime import date, datetime

import pytest

from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.screening.definition import (
    ConstantOperand,
    FactorOperand,
    Predicate,
    ScanUniverse,
    ScreeningCondition,
)
from quant_krx.screening.service import ScreeningService
from quant_krx.storage.db import Database

NOW = datetime(2026, 1, 1)
AS_OF = date(2024, 12, 18)


def _condition(threshold: float = 0.0) -> ScreeningCondition:
    return ScreeningCondition(
        id="c1", name="종가 조건", version="1",
        universe=ScanUniverse(market="KRX", exclusion_filters=frozenset()),
        root=Predicate(
            left=FactorOperand(factor_id="price", column="close"),
            operator=">",
            right=ConstantOperand(value=threshold),
        ),
    )


class _CountingAdapter(FixtureAdapter):
    """스크리닝이 실제로 재실행됐는지 세기 위한 계측 어댑터."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.metadata_calls = 0

    def fetch_metadata(self, symbols):
        self.metadata_calls += 1
        return super().fetch_metadata(symbols)


@pytest.fixture()
def service(tmp_path):
    db = Database(path=tmp_path / "cache.duckdb")
    db.connect()
    provider = _CountingAdapter()
    svc = ScreeningService(db, provider)
    svc.upsert_condition(_condition(), now=NOW)
    yield svc, provider, db
    db.close()


def test_resolve_symbols_returns_codes_only(service):
    svc, _, _ = service
    symbols = svc.resolve_symbols("c1", AS_OF)
    assert symbols
    assert all(isinstance(s, str) and len(s) == 6 for s in symbols)


def test_second_call_hits_cache_without_rerunning(service):
    svc, provider, _ = service
    first = svc.resolve_symbols("c1", AS_OF)
    calls_after_first = provider.metadata_calls

    second = svc.resolve_symbols("c1", AS_OF)

    assert second == first
    assert provider.metadata_calls == calls_after_first, "캐시 히트는 재실행하지 않는다"


def test_use_cache_false_reruns(service):
    svc, provider, _ = service
    svc.resolve_symbols("c1", AS_OF)
    calls_after_first = provider.metadata_calls

    svc.resolve_symbols("c1", AS_OF, use_cache=False)

    assert provider.metadata_calls > calls_after_first


def test_different_as_of_is_cached_separately(service):
    svc, provider, _ = service
    svc.resolve_symbols("c1", AS_OF)
    calls_after_first = provider.metadata_calls

    svc.resolve_symbols("c1", date(2024, 6, 28))

    assert provider.metadata_calls > calls_after_first, "다른 시점은 새로 계산해야 한다"


def test_condition_change_invalidates_cache(service):
    """조건 본문이 바뀌면 캐시 키(해시)가 달라져 자동 무효화된다."""
    svc, provider, _ = service
    first = svc.resolve_symbols("c1", AS_OF)

    svc.upsert_condition(_condition(threshold=10_000_000.0), now=NOW)  # 아무도 통과 못 하는 조건
    second = svc.resolve_symbols("c1", AS_OF)

    assert first != second
    assert second == []


def test_deleting_condition_clears_its_cache(service):
    """조건을 지우면 캐시도 지워져 같은 id 재생성 시 옛 결과가 되살아나지 않는다."""
    svc, _, db = service
    svc.resolve_symbols("c1", AS_OF)

    svc.delete_condition("c1")

    with db.cursor() as conn:
        remaining = conn.execute(
            "SELECT count(*) FROM screening_result_cache WHERE condition_id='c1'"
        ).fetchone()[0]
    assert remaining == 0


def test_clear_cache_removes_entries(service):
    svc, _, _ = service
    svc.resolve_symbols("c1", AS_OF)
    svc.resolve_symbols("c1", date(2024, 6, 28))

    removed = svc.clear_cache("c1")

    assert removed == 2
    assert svc.clear_cache("c1") == 0


def test_resolve_symbols_unknown_condition_fails(service):
    from quant_krx.screening.errors import ScreeningError

    svc, _, _ = service
    with pytest.raises(ScreeningError, match="찾을 수 없습니다"):
        svc.resolve_symbols("no_such", AS_OF)
