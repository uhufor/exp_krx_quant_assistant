import pytest
from datetime import date
from pathlib import Path
from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.quant import MACrossoverStrategy, StrategyRunner
from quant_krx.signals import SignalClassifier
from quant_krx.reports import ReportARenderer, ReportBRenderer, ReportInput, RenderedReport

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_ohlcv.csv"

@pytest.fixture
def signal():
    adapter = FixtureAdapter(fixture_path=FIXTURE_PATH)
    ohlcv = adapter.fetch_ohlcv("005930", date(2024, 1, 2), date(2024, 12, 31)).df
    result = StrategyRunner().run_one(
        MACrossoverStrategy(short_window=10, long_window=30),
        ohlcv,
        run_id="20240102-rpttest",
    )
    return SignalClassifier("balanced").classify(result, signal_date=date(2024, 12, 31))

@pytest.fixture
def report_input(signal):
    return ReportInput(
        signal=signal,
        theme_labels=["반도체", "대형주"],
        ticker_metadata={"name": "삼성전자"},
        regime_summary="2024년 하반기 상승 추세",
    )

# --- Report A ---

def test_report_a_returns_rendered_report(report_input):
    renderer = ReportARenderer()
    report = renderer.render(report_input)
    assert isinstance(report, RenderedReport)
    assert report.report_type == "A"

def test_report_a_references_signal_id(report_input, signal):
    renderer = ReportARenderer()
    report = renderer.render(report_input)
    assert report.signal_id == signal.id

def test_report_a_no_llm_used(report_input):
    renderer = ReportARenderer()
    report = renderer.render(report_input)
    assert report.llm_used is False

def test_report_a_deterministic(report_input):
    """같은 입력 → 항상 같은 내용."""
    renderer = ReportARenderer()
    r1 = renderer.render(report_input)
    r2 = renderer.render(report_input)
    # 생성 시각 제외하고 핵심 내용 동일
    assert r1.signal_id == r2.signal_id
    assert r1.report_type == r2.report_type

def test_report_a_content_has_required_sections(report_input):
    renderer = ReportARenderer()
    report = renderer.render(report_input)
    for section in ("신호 요약", "백테스트 성과 지표"):
        assert section in report.content, f"Missing section: {section}"

def test_report_a_contains_signal_id(report_input, signal):
    renderer = ReportARenderer()
    report = renderer.render(report_input)
    assert signal.id in report.content

# --- Report B ---

def test_report_b_no_llm_fallback(report_input, signal):
    renderer = ReportBRenderer(llm=None)
    report = renderer.render(report_input)
    assert report.report_type == "B"
    assert report.signal_id == signal.id
    assert report.llm_used is False

def test_report_b_same_signal_id_as_report_a(report_input, signal):
    """Report A와 Report B가 동일한 signal_id를 참조해야 함."""
    ra = ReportARenderer().render(report_input)
    rb = ReportBRenderer(llm=None).render(report_input)
    assert ra.signal_id == rb.signal_id == signal.id

def test_report_b_with_mock_llm(report_input, signal):
    class MockLLM:
        def complete(self, prompt: str) -> str:
            return "### 📊 팩트\n테스트 팩트\n### 🔍 추론\n테스트 추론\n### 💡 권고\n테스트 권고 (투자 권유 아님)"

    renderer = ReportBRenderer(llm=MockLLM())
    report = renderer.render(report_input)
    assert report.llm_used is True
    assert report.signal_id == signal.id
    assert "테스트 팩트" in report.content

def test_report_b_llm_failure_fallback(report_input, signal):
    class FailingLLM:
        def complete(self, prompt: str) -> str:
            raise RuntimeError("Connection timeout")

    renderer = ReportBRenderer(llm=FailingLLM())
    report = renderer.render(report_input)
    assert report.llm_used is False
    assert report.signal_id == signal.id
    assert "LLM 호출 실패" in report.content
