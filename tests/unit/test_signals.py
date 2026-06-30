import pytest
from datetime import date
from pathlib import Path
from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.quant import MACrossoverStrategy, RSIBreakoutStrategy, StrategyRunner
from quant_krx.signals import Signal, SignalType, SignalClassifier

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_ohlcv.csv"

@pytest.fixture
def backtest_result():
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    ohlcv = adapter.fetch_ohlcv("005930", date(2024, 1, 2), date(2024, 12, 31)).df
    strategy = MACrossoverStrategy(short_window=10, long_window=30)
    runner = StrategyRunner()
    return runner.run_one(strategy, ohlcv, run_id="20240102-testtest")

def test_classify_returns_signal(backtest_result):
    classifier = SignalClassifier("balanced")
    signal = classifier.classify(backtest_result, signal_date=date(2024, 12, 31))
    assert isinstance(signal, Signal)
    assert signal.symbol == "005930"
    assert signal.run_id == "20240102-testtest"
    assert signal.signal_date == date(2024, 12, 31)

def test_signal_type_is_valid_enum(backtest_result):
    classifier = SignalClassifier("balanced")
    signal = classifier.classify(backtest_result)
    assert isinstance(signal.signal_type, SignalType)
    assert signal.signal_type in list(SignalType)

def test_signal_has_evidence_metrics(backtest_result):
    classifier = SignalClassifier("balanced")
    signal = classifier.classify(backtest_result)
    m = signal.evidence_metrics
    assert isinstance(m.total_return, float)
    assert isinstance(m.mdd, float)
    assert m.mdd >= 0

def test_signal_score_range(backtest_result):
    classifier = SignalClassifier("balanced")
    signal = classifier.classify(backtest_result)
    assert 0.0 <= signal.score <= 1.0

def test_signal_has_run_id(backtest_result):
    classifier = SignalClassifier("balanced")
    signal = classifier.classify(backtest_result)
    assert signal.run_id == "20240102-testtest"
    assert signal.id != signal.run_id  # signal id ≠ run_id

def test_signal_to_dict_has_required_keys(backtest_result):
    classifier = SignalClassifier("balanced")
    signal = classifier.classify(backtest_result)
    d = signal.to_dict()
    for key in ("id", "run_id", "symbol", "signal_date", "signal_type", "score", "risk_flags", "metrics"):
        assert key in d, f"Missing key: {key}"

def test_high_mdd_adds_risk_flag():
    """MDD가 임계값 초과 시 risk_flag 추가."""
    from quant_krx.quant.base import BacktestMetrics, BacktestResult
    import pandas as pd
    metrics = BacktestMetrics(
        total_return=0.5,
        benchmark_return=0.1,
        excess_return=0.4,
        mdd=0.45,          # 45% > 30% 임계값
        sharpe=1.5,
        sortino=1.8,
        trade_count=10,
        fees_paid=0.01,
        slippage_cost=0.005,
        recent_6m_return=0.05,
        recent_12m_return=0.08,
        win_rate=0.6,
    )
    result = BacktestResult(
        symbol="TEST",
        strategy_name="test",
        params={},
        start=date(2024, 1, 2),
        end=date(2024, 12, 31),
        metrics=metrics,
        trades=pd.DataFrame(),
        equity_curve=pd.Series(dtype=float),
        run_id="20240102-testtest",
    )
    classifier = SignalClassifier("balanced")
    signal = classifier.classify(result)
    assert any("HIGH_MDD" in f for f in signal.risk_flags)

def test_classify_batch(backtest_result):
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    results = []
    for sym in ["005930", "000660"]:
        ohlcv = adapter.fetch_ohlcv(sym, date(2024, 1, 2), date(2024, 12, 31)).df
        strategy = MACrossoverStrategy(short_window=10, long_window=30)
        runner = StrategyRunner()
        results.append(runner.run_one(strategy, ohlcv))

    classifier = SignalClassifier("balanced")
    signals = classifier.classify_batch(results)
    assert len(signals) == 2
    assert all(isinstance(s, Signal) for s in signals)
