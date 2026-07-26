from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_krx.screening.definition import Composition, RankPredicate
from quant_krx.screening.errors import ScreeningError
from quant_krx.screening.ranking import apply_rank_predicates, compute_cross_sectional_rank

AS_OF = date(2026, 1, 15)


class _RecordingSnapshotProvider:
    """fetch_market_snapshot 호출 횟수/인자를 기록하는 스텁 provider."""

    source_name = "Stub"

    def __init__(self, snapshot: pd.DataFrame) -> None:
        self._snapshot = snapshot
        self.calls: list[tuple[date, str]] = []

    def fetch_market_snapshot(self, date_, market: str = "KRX") -> pd.DataFrame:
        self.calls.append((date_, market))
        return self._snapshot.copy()


def _make_snapshot(n: int) -> pd.DataFrame:
    """symbol 000001..NNN, trading_value는 symbol 번호와 정비례(값이 클수록 순위 상위)."""
    symbols = [f"{i:06d}" for i in range(1, n + 1)]
    trading_values = [float(i) for i in range(1, n + 1)]
    return pd.DataFrame(
        {
            "symbol": symbols,
            "close": [100.0] * n,
            "volume": [1000 * i for i in range(1, n + 1)],
            "trading_value": trading_values,
        }
    )


class TestComputeCrossSectionalRank:
    def test_desc_top_100_boundary_of_150(self):
        """150개 종목 중 거래대금 상위 100개만 통과 — 100위/101위 경계 정확성."""
        snapshot = _make_snapshot(150)
        provider = _RecordingSnapshotProvider(snapshot)
        symbols = snapshot["symbol"].tolist()
        predicate = RankPredicate(
            factor_id="trading_value", column="trading_value", rank_metric="desc", top_n=100
        )

        result = compute_cross_sectional_rank(
            provider, symbols, as_of=AS_OF, market="KRX", rank_predicate=predicate
        )

        assert len(result) == 100
        # trading_value는 symbol 번호와 정비례하므로 상위 100은 051~150.
        assert "000150" in result  # 1위(최댓값)
        assert "000051" in result  # 100위(경계 통과)
        assert "000050" not in result  # 101위(경계 탈락)

    def test_calls_fetch_market_snapshot_exactly_once(self):
        snapshot = _make_snapshot(10)
        provider = _RecordingSnapshotProvider(snapshot)
        symbols = snapshot["symbol"].tolist()
        predicate = RankPredicate(
            factor_id="trading_value", column="trading_value", rank_metric="desc", top_n=5
        )

        compute_cross_sectional_rank(
            provider, symbols, as_of=AS_OF, market="KRX", rank_predicate=predicate
        )

        assert provider.calls == [(AS_OF, "KRX")]

    def test_rank_metric_asc_selects_lowest_values(self):
        snapshot = _make_snapshot(10)
        provider = _RecordingSnapshotProvider(snapshot)
        symbols = snapshot["symbol"].tolist()
        predicate = RankPredicate(
            factor_id="trading_value", column="trading_value", rank_metric="asc", top_n=3
        )

        result = compute_cross_sectional_rank(
            provider, symbols, as_of=AS_OF, market="KRX", rank_predicate=predicate
        )

        assert result == {"000001", "000002", "000003"}

    def test_rank_metric_desc_selects_highest_values(self):
        snapshot = _make_snapshot(10)
        provider = _RecordingSnapshotProvider(snapshot)
        symbols = snapshot["symbol"].tolist()
        predicate = RankPredicate(
            factor_id="trading_value", column="trading_value", rank_metric="desc", top_n=3
        )

        result = compute_cross_sectional_rank(
            provider, symbols, as_of=AS_OF, market="KRX", rank_predicate=predicate
        )

        assert result == {"000010", "000009", "000008"}

    def test_ties_use_min_rank_method(self):
        """동점(공동 1위 2개)이 있을 때 method='min' 의미론 검증: top_n=2면 3개 모두 통과."""
        snapshot = pd.DataFrame(
            {
                "symbol": ["000001", "000002", "000003", "000004"],
                "close": [100.0] * 4,
                "volume": [1000] * 4,
                "trading_value": [50.0, 50.0, 30.0, 10.0],
            }
        )
        provider = _RecordingSnapshotProvider(snapshot)
        symbols = snapshot["symbol"].tolist()
        predicate = RankPredicate(
            factor_id="trading_value", column="trading_value", rank_metric="desc", top_n=2
        )

        result = compute_cross_sectional_rank(
            provider, symbols, as_of=AS_OF, market="KRX", rank_predicate=predicate
        )

        # 000001/000002 공동 1위(rank=1), 000003은 rank=3(2가 아님) -> top_n=2 이내 통과는 2종목뿐.
        assert result == {"000001", "000002"}

    def test_symbols_missing_from_snapshot_are_excluded_naturally(self):
        snapshot = _make_snapshot(5)
        provider = _RecordingSnapshotProvider(snapshot)
        # "999999"는 스냅샷에 없는 상장폐지 종목 가정.
        symbols = snapshot["symbol"].tolist() + ["999999"]
        predicate = RankPredicate(
            factor_id="trading_value", column="trading_value", rank_metric="desc", top_n=10
        )

        result = compute_cross_sectional_rank(
            provider, symbols, as_of=AS_OF, market="KRX", rank_predicate=predicate
        )

        assert "999999" not in result
        assert result == {"000001", "000002", "000003", "000004", "000005"}

    def test_volume_column_ranking(self):
        snapshot = _make_snapshot(10)
        provider = _RecordingSnapshotProvider(snapshot)
        symbols = snapshot["symbol"].tolist()
        predicate = RankPredicate(
            factor_id="volume", column="volume", rank_metric="desc", top_n=1
        )

        result = compute_cross_sectional_rank(
            provider, symbols, as_of=AS_OF, market="KRX", rank_predicate=predicate
        )

        assert result == {"000010"}

    def test_unsupported_column_raises_screening_error(self):
        snapshot = _make_snapshot(5)
        provider = _RecordingSnapshotProvider(snapshot)
        symbols = snapshot["symbol"].tolist()
        predicate = RankPredicate(
            factor_id="pe_ratio", column="pe_ratio", rank_metric="asc", top_n=1
        )

        with pytest.raises(ScreeningError):
            compute_cross_sectional_rank(
                provider, symbols, as_of=AS_OF, market="KRX", rank_predicate=predicate
            )


class TestApplyRankPredicates:
    def test_maps_each_rank_predicate_to_its_result_set(self):
        snapshot = _make_snapshot(10)
        provider = _RecordingSnapshotProvider(snapshot)
        symbols = snapshot["symbol"].tolist()
        predicate_a = RankPredicate(
            factor_id="trading_value", column="trading_value", rank_metric="desc", top_n=3
        )
        predicate_b = RankPredicate(
            factor_id="volume", column="volume", rank_metric="asc", top_n=2
        )
        node = Composition(op="AND", operands=(predicate_a, predicate_b))

        result = apply_rank_predicates(
            node, provider=provider, symbols=symbols, as_of=AS_OF, market="KRX"
        )

        assert result[predicate_a] == {"000010", "000009", "000008"}
        assert result[predicate_b] == {"000001", "000002"}
        # 스냅샷은 서로 다른 두 predicate 각각에 대해 1번씩, 총 2번 호출.
        assert len(provider.calls) == 2

    def test_no_rank_predicates_returns_empty_dict(self):
        from quant_krx.screening.definition import ConstantOperand, Predicate

        snapshot = _make_snapshot(5)
        provider = _RecordingSnapshotProvider(snapshot)
        node = Predicate(
            left=ConstantOperand(value=1), operator=">", right=ConstantOperand(value=0)
        )

        result = apply_rank_predicates(
            node, provider=provider, symbols=["000001"], as_of=AS_OF, market="KRX"
        )

        assert result == {}
        assert provider.calls == []
