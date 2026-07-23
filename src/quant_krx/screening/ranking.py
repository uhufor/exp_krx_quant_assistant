from __future__ import annotations

from datetime import date

from quant_krx.data.base import DataProvider
from quant_krx.screening.definition import Node, RankPredicate
from quant_krx.screening.errors import ScreeningError
from quant_krx.screening.evaluation import extract_rank_predicates

# fetch_market_snapshot()이 반환하는 네이티브 컬럼(계약: data/base.py::DataProvider 참조).
_SNAPSHOT_COLUMNS = frozenset({"close", "volume", "trading_value"})


def compute_cross_sectional_rank(
    provider: DataProvider,
    symbols: list[str],
    *,
    as_of: date,
    market: str,
    rank_predicate: RankPredicate,
) -> set[str]:
    """단일 RankPredicate를 시장 스냅샷 1회 조회로 평가해 상위 top_n 종목 집합을 반환한다.

    provider.fetch_market_snapshot()을 정확히 1번만 호출한다(종목별 순차 호출 금지 —
    이 스토리의 핵심 성능 요구사항). rank_predicate.column은 스냅샷의 네이티브 컬럼
    (close/volume/trading_value) 중 하나를 가리켜야 한다 — factors/의 동명 팩터(근사치)는
    사용하지 않는다(스냅샷 값이 진실 원천).

    스냅샷에 없는 symbol(상장폐지/데이터 부재 등)은 자동으로 순위 계산에서 제외된다
    (에러 아님, 자연스러운 결측 처리).
    """
    if rank_predicate.column not in _SNAPSHOT_COLUMNS:
        raise ScreeningError(
            f"RankPredicate.column '{rank_predicate.column}'은 시장 스냅샷 네이티브 컬럼이"
            f" 아닙니다(허용: {sorted(_SNAPSHOT_COLUMNS)})"
        )

    snapshot = provider.fetch_market_snapshot(as_of, market)
    filtered = snapshot[snapshot["symbol"].isin(symbols)]

    ranks = filtered[rank_predicate.column].rank(
        method="min", ascending=(rank_predicate.rank_metric == "asc")
    )
    passed = filtered.loc[ranks <= rank_predicate.top_n, "symbol"]
    return set(passed)


def apply_rank_predicates(
    node: Node,
    *,
    provider: DataProvider,
    symbols: list[str],
    as_of: date,
    market: str,
) -> dict[RankPredicate, set[str]]:
    """조건 트리의 모든 RankPredicate를 찾아 순위 통과 종목 집합으로 매핑한다.

    RankPredicate는 CanonicalEq 기반 값 동등성/해시를 가지므로(동일 정의 → 동일 키)
    dict 키로 직접 사용할 수 있다. 다음 스토리(ScreeningService.run())는 조건 트리 평가 중
    RankPredicate 리프를 만나면 이 매핑에서 결과 집합을 조회해 대입한다.
    """
    predicates = extract_rank_predicates(node)
    return {
        predicate: compute_cross_sectional_rank(
            provider,
            symbols,
            as_of=as_of,
            market=market,
            rank_predicate=predicate,
        )
        for predicate in predicates
    }
