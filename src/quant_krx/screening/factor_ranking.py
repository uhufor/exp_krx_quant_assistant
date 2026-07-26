from __future__ import annotations

from datetime import date

import pandas as pd

from quant_krx.data.loader import load_factor_input
from quant_krx.factors import FactorInput, compute_factor, get_factor
from quant_krx.screening.definition import FactorRankPredicate, Node
from quant_krx.screening.evaluation import extract_factor_rank_predicates
from quant_krx.storage.db import Database


def compute_cross_sectional_factor_rank(
    db: Database,
    symbols: list[str],
    *,
    as_of: date,
    rank_predicate: FactorRankPredicate,
) -> set[str]:
    """FactorRankPredicate 하나를 종목별 DB 재무/밸류에이션 as-of 값으로 평가해 top_n
    종목 집합을 반환한다(TRD-R04 §4.3).

    재무제표 14종·밸류에이션 11종 팩터는 `.compute()`가 `data.ohlcv.index`를 as-of 병합
    기준으로만 쓰고 실제 가격 값은 참조하지 않는다(TRD-R04 §0 확인 완료) — 따라서 인덱스만
    있는 더미 프레임으로 기존 `compute_factor`를 그대로 재사용해 종목별 OHLCV 조회 없이
    값을 얻는다(백테스트와 완전히 동일한 산식 보장, 계산 로직 재구현 없음).
    """
    factor = get_factor(rank_predicate.factor_id, **dict(rank_predicate.params))
    dummy_ohlcv = pd.DataFrame(index=pd.DatetimeIndex([pd.Timestamp(as_of)]))

    values: dict[str, float] = {}
    with db.cursor() as conn:
        for symbol in symbols:
            try:
                bundle = load_factor_input(conn, symbol, end=as_of, ohlcv=dummy_ohlcv)
                factor_input = FactorInput(
                    ohlcv=dummy_ohlcv, valuation=bundle.valuation, financials=bundle.financials
                )
                result_df = compute_factor(factor, factor_input)
            except Exception:  # noqa: BLE001 — 종목 단위 결측/오류는 순위에서 자연 제외
                continue
            if rank_predicate.column not in result_df.columns:
                continue
            value = result_df[rank_predicate.column].iloc[-1]
            if pd.notna(value):
                values[symbol] = float(value)

    if not values:
        return set()
    series = pd.Series(values)
    ranks = series.rank(method="min", ascending=(rank_predicate.rank_metric == "asc"))
    return set(ranks[ranks <= rank_predicate.top_n].index)


def apply_factor_rank_predicates(
    node: Node,
    *,
    db: Database,
    symbols: list[str],
    as_of: date,
) -> dict[FactorRankPredicate, set[str]]:
    """조건 트리의 모든 FactorRankPredicate를 찾아 순위 통과 종목 집합으로 매핑한다."""
    predicates = extract_factor_rank_predicates(node)
    return {
        predicate: compute_cross_sectional_factor_rank(
            db, symbols, as_of=as_of, rank_predicate=predicate
        )
        for predicate in predicates
    }
