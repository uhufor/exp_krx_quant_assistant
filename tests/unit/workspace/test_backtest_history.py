from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from quant_krx.factors import FactorInput
from quant_krx.rule.definition import FactorOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.service import WorkspaceService

NOW = datetime(2026, 1, 1, 0, 0, 0)
START = date(2024, 1, 1)
END = date(2024, 9, 26)


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes, "high": closes, "low": closes,
            "close": closes, "volume": [1000.0] * len(closes),
        },
        index=index,
    )


def _wave(n: int = 270) -> list[float]:
    """상승/하락이 번갈아 나와 SMA 교차(진입·청산)가 실제로 발생하는 합성 가격."""
    return [100.0 + 20.0 * ((i // 30) % 2) + (i % 30) * 0.5 for i in range(n)]


@pytest.fixture()
def svc(tmp_path):
    db = Database(path=tmp_path / "history.duckdb")
    db.connect()
    service = WorkspaceService(db)
    rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    service.upsert_rule(rule, now=NOW)
    service.upsert_strategy(
        StrategyDefinition(
            id="s1", name="s1", version="1",
            factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
            universe=Universe(symbols=("005930",)),
            rule=RuleBinding(entry=("entry_rule",)),
        ),
        now=NOW,
    )
    yield service
    db.close()


def _data(closes: list[float] | None = None) -> dict[str, FactorInput]:
    return {"005930": FactorInput(ohlcv=_ohlcv(closes or _wave()), valuation=None, financials=None)}


def _run(svc: WorkspaceService, data=None, **kwargs):
    params = {
        "data": data or _data(), "start": START, "end": END,
        "fees": 0.003, "slippage": 0.001, "data_source": "fixture",
    }
    params.update(kwargs)
    return svc.backtest("s1", **params)


def test_backtest_persists_run_history(svc):
    report = _run(svc)

    assert report.run_id, "실행에는 run_id가 부여되어야 한다"
    assert report.from_cache is False
    records = svc.list_backtest_runs()
    assert len(records) == 1
    assert records[0]["run_id"] == report.run_id
    assert records[0]["strategy_id"] == "s1"
    assert records[0]["params"]["data_source"] == "fixture"


def test_identical_rerun_hits_cache_without_new_history_row(svc):
    first = _run(svc)
    second = _run(svc)

    assert second.from_cache is True
    assert second.run_id == first.run_id, "캐시 히트는 원 실행의 run_id를 그대로 돌려준다"
    assert len(svc.list_backtest_runs()) == 1, "캐시 히트는 이력을 새로 쌓지 않는다"


def test_cached_report_preserves_metrics(svc):
    first = _run(svc)
    second = _run(svc)

    assert second.metrics.total_return == pytest.approx(first.metrics.total_return)
    assert second.metrics.mdd == pytest.approx(first.metrics.mdd)
    assert second.metrics.trade_count == first.metrics.trade_count
    assert set(second.per_symbol) == set(first.per_symbol)


def test_cached_report_preserves_equity_curve(svc):
    first = _run(svc)
    second = _run(svc)

    original = first.results["005930"].equity_curve
    restored = second.results["005930"].equity_curve
    pd.testing.assert_series_equal(
        original.astype(float), restored, check_names=False, check_freq=False
    )


def test_cached_report_has_no_trades(svc):
    """거래내역은 저장하지 않으므로 캐시 복원 결과는 빈 DataFrame이어야 한다(미저장 계약)."""
    _run(svc)
    cached = _run(svc)
    assert cached.from_cache is True
    assert cached.results["005930"].trades.empty


def test_no_cache_forces_recomputation_and_new_history_row(svc):
    first = _run(svc)
    second = _run(svc, use_cache=False)

    assert second.from_cache is False
    assert second.run_id != first.run_id
    assert len(svc.list_backtest_runs()) == 2


def test_changed_data_invalidates_cache(svc):
    """데이터가 갱신되면 커버리지 지문이 바뀌어 캐시가 자동 무효화된다(낡은 결과 방지)."""
    _run(svc)
    changed = _run(svc, data=_data(_wave(280)))

    assert changed.from_cache is False
    assert len(svc.list_backtest_runs()) == 2


def test_corrected_past_value_invalidates_cache(svc):
    """행 수·기간이 그대로여도 과거 값이 정정되면 캐시가 무효화되어야 한다."""
    baseline = _wave()
    _run(svc, data=_data(baseline))

    corrected = list(baseline)
    corrected[10] = corrected[10] + 37.0
    result = _run(svc, data=_data(corrected))

    assert result.from_cache is False


def test_changed_parameters_invalidate_cache(svc):
    _run(svc)
    assert _run(svc, fees=0.01).from_cache is False


def test_changed_rule_invalidates_cache(svc):
    """전략 본문이 아니라 전이 참조 Rule만 바뀌어도 캐시가 무효화되어야 한다."""
    _run(svc)
    svc.upsert_rule(
        Rule(
            id="entry_rule", name="entry", version="2",
            root=Predicate(
                FactorOperand("sma", "sma", {"window": 5}), "<",
                FactorOperand("sma", "sma", {"window": 20}),
            ),
        ),
        now=NOW,
    )
    assert _run(svc).from_cache is False


def test_get_backtest_run_restores_report(svc):
    report = _run(svc)
    restored = svc.get_backtest_run(report.run_id)

    assert restored is not None
    assert restored.from_cache is True
    assert restored.metrics.total_return == pytest.approx(report.metrics.total_return)


def test_get_backtest_run_missing_returns_none(svc):
    assert svc.get_backtest_run("no-such-run") is None


def test_list_backtest_runs_filters_by_strategy(svc):
    _run(svc)
    assert len(svc.list_backtest_runs(strategy_id="s1")) == 1
    assert svc.list_backtest_runs(strategy_id="other") == []


def test_delete_backtest_run(svc):
    report = _run(svc)
    svc.delete_backtest_run(report.run_id)
    assert svc.list_backtest_runs() == []
