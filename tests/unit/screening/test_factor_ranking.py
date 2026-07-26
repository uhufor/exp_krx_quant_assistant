from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.data.upsert import upsert_fundamental
from quant_krx.screening.definition import Composition, FactorRankPredicate
from quant_krx.screening.factor_ranking import (
    apply_factor_rank_predicates,
    compute_cross_sectional_factor_rank,
)
from quant_krx.storage.db import Database

AS_OF = date(2026, 1, 15)


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "test.duckdb")
    database.connect()
    yield database
    database.close()


def _financials_row(
    symbol: str,
    *,
    total_debt: float,
    total_equity: float,
    disclosure_date: date = date(2025, 8, 14),
) -> dict:
    return {
        "symbol": symbol, "fiscal_year": 2025, "fiscal_quarter": 2,
        "statement_scope": "consolidated",
        "revenue": 100.0, "gross_profit": 50.0, "operating_income": 30.0,
        "net_income": 20.0, "pretax_income": 25.0, "income_tax": 5.0,
        "total_assets": total_debt + total_equity, "total_debt": total_debt,
        "total_equity": total_equity, "current_assets": 500.0, "current_liabilities": 200.0,
        "operating_cash_flow": 40.0, "interest_expense": 2.0,
        "depreciation_amortization": 10.0, "cash_and_equivalents": 100.0,
        "invested_capital": total_debt + total_equity,
        "period_end": date(2025, 6, 30), "disclosure_date": disclosure_date,
    }


def _seed_financials(db: Database, rows: list[dict], *, as_of: date = AS_OF) -> None:
    frame = pd.DataFrame(rows).assign(source="dart", fetched_at=date.today())
    with db.cursor() as conn:
        upsert_fundamental(conn, "financial_statements", frame, as_of=as_of)


class TestComputeCrossSectionalFactorRank:
    def test_ranks_by_debt_to_equity_without_touching_ohlcv(self, db):
        """TRD-R04 §0 핵심 전제 검증 — OHLCV 테이블에 아무것도 없어도(§ohlcv_daily 미기록)
        재무 팩터 순위 계산이 정상 동작해야 한다."""
        _seed_financials(
            db,
            [
                _financials_row("000001", total_debt=100.0, total_equity=100.0),  # d/e = 1.0
                _financials_row("000002", total_debt=400.0, total_equity=100.0),  # d/e = 4.0
                _financials_row("000003", total_debt=50.0, total_equity=100.0),  # d/e = 0.5
            ],
        )
        predicate = FactorRankPredicate(
            factor_id="debt_to_equity", column="debt_to_equity", rank_metric="asc", top_n=2
        )

        result = compute_cross_sectional_factor_rank(
            db, ["000001", "000002", "000003"], as_of=AS_OF, rank_predicate=predicate
        )

        # 오름차순 top_n=2 -> 부채비율 낮은 순 2개(000003: 0.5, 000001: 1.0), 000002(4.0) 제외.
        assert result == {"000001", "000003"}

    def test_symbol_without_financials_is_excluded_naturally(self, db):
        _seed_financials(db, [_financials_row("000001", total_debt=100.0, total_equity=100.0)])
        predicate = FactorRankPredicate(
            factor_id="debt_to_equity", column="debt_to_equity", rank_metric="asc", top_n=10
        )

        result = compute_cross_sectional_factor_rank(
            db, ["000001", "999999"], as_of=AS_OF, rank_predicate=predicate
        )

        assert result == {"000001"}
        assert "999999" not in result

    def test_no_data_at_all_returns_empty_set(self, db):
        predicate = FactorRankPredicate(
            factor_id="roic", column="roic", rank_metric="desc", top_n=10
        )
        result = compute_cross_sectional_factor_rank(
            db, ["000001"], as_of=AS_OF, rank_predicate=predicate
        )
        assert result == set()

    def test_disclosure_after_as_of_is_not_visible_yet(self, db):
        """as_of 이후 공시된 분기는 point-in-time 원칙상 아직 반영되면 안 된다(미래 참조 금지).

        upsert 시점의 quality gate(future_date)가 아니라 조회 시점(load_factor_input의
        end=as_of 필터)에서 걸러지는지를 검증하기 위해, 실제 공시일 기준으로는 정상 upsert된
        데이터를 그보다 이른 as_of로 조회한다.
        """
        disclosure = date(2026, 6, 1)
        row = _financials_row(
            "000001", total_debt=100.0, total_equity=100.0, disclosure_date=disclosure
        )
        _seed_financials(db, [row], as_of=disclosure)  # upsert는 공시일 기준으로 정상 통과
        predicate = FactorRankPredicate(
            factor_id="debt_to_equity", column="debt_to_equity", rank_metric="asc", top_n=10
        )

        result = compute_cross_sectional_factor_rank(
            db, ["000001"], as_of=AS_OF, rank_predicate=predicate  # AS_OF(2026-01-15) < 공시일
        )

        assert result == set()  # 아직 공시 전 시점이므로 값이 보이면 안 됨(look-ahead 금지)


class TestApplyFactorRankPredicates:
    def test_maps_each_predicate_to_its_result_set(self, db):
        _seed_financials(
            db,
            [
                _financials_row("000001", total_debt=100.0, total_equity=100.0),
                _financials_row("000002", total_debt=400.0, total_equity=100.0),
            ],
        )
        predicate = FactorRankPredicate(
            factor_id="debt_to_equity", column="debt_to_equity", rank_metric="asc", top_n=1
        )
        node = Composition(op="AND", operands=(predicate, predicate))  # 중복이어도 dict 키는 1개

        result = apply_factor_rank_predicates(
            node, db=db, symbols=["000001", "000002"], as_of=AS_OF
        )

        assert result[predicate] == {"000001"}

    def test_no_factor_rank_predicates_returns_empty_dict(self, db):
        from quant_krx.screening.definition import ConstantOperand, Predicate

        node = Predicate(
            left=ConstantOperand(value=1), operator=">", right=ConstantOperand(value=0)
        )
        result = apply_factor_rank_predicates(node, db=db, symbols=["000001"], as_of=AS_OF)
        assert result == {}
