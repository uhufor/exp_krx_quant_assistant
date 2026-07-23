from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from quant_krx.factors import FactorInput
from quant_krx.rule.definition import FactorOperand, Predicate, Rule
from quant_krx.storage.db import Database
from quant_krx.strategy.definition import FactorRef, RuleBinding, StrategyDefinition, Universe
from quant_krx.workspace.backtest import build_signals, run_single_symbol_backtest
from quant_krx.workspace.errors import EvaluationError, MissingDataError, WorkspaceError
from quant_krx.workspace.evaluation import EvaluationContext
from quant_krx.workspace.service import WorkspaceService

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sample_ohlcv.csv"
NOW = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture(scope="module")
def ohlcv() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE_PATH, dtype={"symbol": str}, parse_dates=["date"])
    df = df[df["symbol"] == "005930"].sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


@pytest.fixture
def svc(tmp_path):
    db = Database(path=tmp_path / "test.duckdb")
    db.connect()
    yield WorkspaceService(db)
    db.close()


def _ma_crossover_strategy(svc: WorkspaceService) -> StrategyDefinition:
    entry_rule = Rule(
        id="entry_rule", name="entry", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 20}), "crosses_above",
            FactorOperand("sma", "sma", {"window": 60}),
        ),
    )
    exit_rule = Rule(
        id="exit_rule", name="exit", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 20}), "crosses_below",
            FactorOperand("sma", "sma", {"window": 60}),
        ),
    )
    svc.upsert_rule(entry_rule, now=NOW)
    svc.upsert_rule(exit_rule, now=NOW)
    defn = StrategyDefinition(
        id="ma_test", name="ma_test", version="1",
        factor_refs=(FactorRef("sma", {"window": 20}), FactorRef("sma", {"window": 60})),
        universe=Universe(),
        rule=RuleBinding(entry=("entry_rule",), exit=("exit_rule",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    return defn


def test_build_signals_entry_exit_and_combination(ohlcv, svc) -> None:
    defn = _ma_crossover_strategy(svc)
    ctx = EvaluationContext(
        data=FactorInput(ohlcv=ohlcv), index=ohlcv.index,
        resolve_formula=svc.get_formula, resolve_rule=svc.get_rule,
    )
    entries, exits = build_signals(defn, ctx)
    assert entries.dtype == bool
    assert exits.dtype == bool
    assert entries.any()
    assert exits.any()


def test_build_signals_no_exit_role_is_all_false(ohlcv, svc) -> None:
    entry_rule = Rule(
        id="entry_only", name="entry", version="1",
        root=Predicate(
            FactorOperand("sma", "sma", {"window": 5}), ">",
            FactorOperand("sma", "sma", {"window": 20}),
        ),
    )
    svc.upsert_rule(entry_rule, now=NOW)
    defn = StrategyDefinition(
        id="no_exit", name="no_exit", version="1",
        factor_refs=(FactorRef("sma", {"window": 5}), FactorRef("sma", {"window": 20})),
        universe=Universe(),
        rule=RuleBinding(entry=("entry_only",)),
    )
    svc.upsert_strategy(defn, now=NOW)
    ctx = EvaluationContext(
        data=FactorInput(ohlcv=ohlcv), index=ohlcv.index,
        resolve_formula=svc.get_formula, resolve_rule=svc.get_rule,
    )
    _, exits = build_signals(defn, ctx)
    assert not exits.any()


def test_build_signals_draft_strategy_rejected(ohlcv, svc) -> None:
    defn = StrategyDefinition(
        id="draft", name="draft", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    ctx = EvaluationContext(
        data=FactorInput(ohlcv=ohlcv), index=ohlcv.index,
        resolve_formula=svc.get_formula, resolve_rule=svc.get_rule,
    )
    with pytest.raises(EvaluationError):
        build_signals(defn, ctx)


def test_service_backtest_produces_minimum_metric_set(ohlcv, svc) -> None:
    defn = _ma_crossover_strategy(svc)
    data = {"005930": FactorInput(ohlcv=ohlcv)}
    report = svc.backtest(defn.id, data=data, fees=0.003, slippage=0.001)

    metrics = report.metrics
    assert isinstance(metrics.total_return, float)
    assert not math.isnan(metrics.mdd)
    assert isinstance(metrics.trade_count, int)
    assert isinstance(metrics.fees_paid, float)
    assert isinstance(metrics.slippage_cost, float)
    assert "005930" in report.per_symbol


def test_service_backtest_exposes_full_results_per_symbol(ohlcv, svc) -> None:
    # BacktestReport.results는 GUI가 equity curve/거래내역을 얻는 유일한 경로(additive 필드).
    defn = _ma_crossover_strategy(svc)
    data = {"005930": FactorInput(ohlcv=ohlcv)}
    report = svc.backtest(defn.id, data=data, fees=0.003, slippage=0.001)

    assert "005930" in report.results
    full_result = report.results["005930"]
    assert isinstance(full_result.trades, pd.DataFrame)
    assert isinstance(full_result.equity_curve, pd.Series)
    assert not full_result.equity_curve.empty
    # GUI 자산곡선에 주가를 겹쳐 보여주기 위한 종가 곡선 — equity_curve와 같은 인덱스.
    assert isinstance(full_result.price, pd.Series)
    assert not full_result.price.empty
    assert list(full_result.price.index) == list(full_result.equity_curve.index)
    assert full_result.metrics == report.per_symbol["005930"]


def test_service_backtest_rejects_non_runnable_strategy(svc) -> None:
    defn = StrategyDefinition(
        id="draft", name="draft", version="1",
        factor_refs=(FactorRef("sma"),), universe=Universe(), rule=None,
    )
    svc.upsert_strategy(defn, now=NOW)
    with pytest.raises(WorkspaceError):
        svc.backtest(defn.id, data={}, fees=0.003, slippage=0.001)


def test_build_signals_enforces_data_contract_missing_valuation(ohlcv, svc) -> None:
    # FR-09: valuation을 요구하는 전략을 valuation=None 데이터로 평가하면
    # build_signals(run_single_symbol_backtest 경유 포함)가 반드시 MissingDataError를 낸다.
    rule = Rule(
        id="per_entry", name="per_entry", version="1",
        root=Predicate(FactorOperand("per", "per"), ">", FactorOperand("per", "per")),
    )
    svc.upsert_rule(rule, now=NOW)
    defn = StrategyDefinition(
        id="per_strategy", name="per_strategy", version="1",
        factor_refs=(FactorRef("per"),), universe=Universe(),
        rule=RuleBinding(entry=("per_entry",)),
    )
    svc.upsert_strategy(defn, now=NOW)

    ctx = EvaluationContext(
        data=FactorInput(ohlcv=ohlcv, valuation=None), index=ohlcv.index,
        resolve_formula=svc.get_formula, resolve_rule=svc.get_rule,
    )
    with pytest.raises(MissingDataError):
        build_signals(defn, ctx)

    with pytest.raises(MissingDataError):
        run_single_symbol_backtest(
            defn, "005930", FactorInput(ohlcv=ohlcv, valuation=None),
            fees=0.003, slippage=0.001, benchmark=None,
            resolve_formula=svc.get_formula, resolve_rule=svc.get_rule,
        )
