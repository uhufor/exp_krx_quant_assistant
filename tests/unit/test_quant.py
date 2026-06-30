import pytest
from datetime import date
from pathlib import Path
import pandas as pd
from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.quant import MACrossoverStrategy, RSIBreakoutStrategy, StrategyRunner, BacktestResult

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_ohlcv.csv"


@pytest.fixture
def ohlcv_005930():
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    data = adapter.fetch_ohlcv("005930", date(2024, 1, 2), date(2024, 12, 31))
    return data.df


@pytest.fixture
def benchmark_df():
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    data = adapter.fetch_benchmark("KOSPI", date(2024, 1, 2), date(2024, 12, 31))
    return data.df


def test_ma_crossover_returns_backtest_result(ohlcv_005930, benchmark_df):
    strategy = MACrossoverStrategy(short_window=10, long_window=30)
    runner = StrategyRunner()
    result = runner.run_one(strategy, ohlcv_005930, benchmark_df, run_id="20240102-test0001")
    assert isinstance(result, BacktestResult)
    assert result.strategy_name == "ma_crossover"
    assert result.run_id == "20240102-test0001"


def test_ma_crossover_metrics_present(ohlcv_005930, benchmark_df):
    strategy = MACrossoverStrategy(short_window=10, long_window=30)
    runner = StrategyRunner()
    result = runner.run_one(strategy, ohlcv_005930, benchmark_df)
    m = result.metrics
    # 필수 메트릭 존재 확인
    assert isinstance(m.total_return, float)
    assert isinstance(m.mdd, float)
    assert isinstance(m.sharpe, float)
    assert isinstance(m.trade_count, int)
    assert isinstance(m.recent_6m_return, float)
    assert isinstance(m.recent_12m_return, float)
    # MDD는 양수 (최대낙폭)
    assert m.mdd >= 0


def test_ma_crossover_reproducible(ohlcv_005930, benchmark_df):
    """같은 입력 → 같은 결과 (재현 가능성)."""
    strategy = MACrossoverStrategy(short_window=10, long_window=30)
    runner = StrategyRunner()
    r1 = runner.run_one(strategy, ohlcv_005930, benchmark_df, run_id="repro-test")
    r2 = runner.run_one(strategy, ohlcv_005930, benchmark_df, run_id="repro-test")
    assert abs(r1.metrics.total_return - r2.metrics.total_return) < 1e-10
    assert abs(r1.metrics.mdd - r2.metrics.mdd) < 1e-10


def test_rsi_breakout_returns_backtest_result(ohlcv_005930, benchmark_df):
    strategy = RSIBreakoutStrategy(rsi_window=14, oversold=30.0, overbought=70.0)
    runner = StrategyRunner()
    result = runner.run_one(strategy, ohlcv_005930, benchmark_df)
    assert isinstance(result, BacktestResult)
    assert result.strategy_name == "rsi_breakout"


def test_rsi_breakout_metrics_present(ohlcv_005930, benchmark_df):
    strategy = RSIBreakoutStrategy()
    runner = StrategyRunner()
    result = runner.run_one(strategy, ohlcv_005930, benchmark_df)
    m = result.metrics
    assert isinstance(m.total_return, float)
    assert isinstance(m.mdd, float)
    assert m.mdd >= 0


def test_batch_run(ohlcv_005930):
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    ohlcv_map = {}
    for sym in ["005930", "000660"]:
        d = adapter.fetch_ohlcv(sym, date(2024, 1, 2), date(2024, 12, 31))
        ohlcv_map[sym] = d.df
    strategies = [
        MACrossoverStrategy(short_window=10, long_window=30),
        RSIBreakoutStrategy(),
    ]
    runner = StrategyRunner()
    results = runner.run_batch(strategies, ohlcv_map)
    assert len(results) == 4  # 2 symbols × 2 strategies


def test_equity_curve_present(ohlcv_005930, benchmark_df):
    strategy = MACrossoverStrategy(short_window=10, long_window=30)
    runner = StrategyRunner()
    result = runner.run_one(strategy, ohlcv_005930, benchmark_df)
    assert result.equity_curve is not None
    assert len(result.equity_curve) > 0
