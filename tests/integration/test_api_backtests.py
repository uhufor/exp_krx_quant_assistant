from __future__ import annotations

from fastapi.testclient import TestClient

from quant_krx.api.app import create_app
from quant_krx.api.deps import get_db
from quant_krx.config.settings import Settings, get_settings
from quant_krx.storage.db import Database

ENTRY_RULE = {
    "name": "entry",
    "version": "1",
    "root": {
        "node": "predicate",
        "left": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 20}},
        "operator": "crosses_above",
        "right": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 60}},
    },
}
EXIT_RULE = {
    "name": "exit",
    "version": "1",
    "root": {
        "node": "predicate",
        "left": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 20}},
        "operator": "crosses_below",
        "right": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 60}},
    },
}
STRATEGY_BODY = {
    "name": "테스트 전략",
    "version": "1",
    "factor_refs": [
        {"factor_id": "sma", "params": {"window": 20}},
        {"factor_id": "sma", "params": {"window": 60}},
    ],
    "universe": {"symbols": []},
    "rule": {"roles": {"entry": ["entry_rule"], "exit": ["exit_rule"]}},
}


def _client(tmp_path) -> TestClient:
    app = create_app()
    test_settings = Settings(
        duckdb_path=str(tmp_path / "test.duckdb"),
        watchlist_path=str(tmp_path / "no_such_watchlist.yaml"),  # 실제 프로젝트 watchlist 격리
    )

    def _override_get_db():
        db = Database(path=tmp_path / "test.duckdb")
        db.connect()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings
    return TestClient(app)


def _seed_runnable_strategy(client: TestClient) -> None:
    client.put("/api/rules/entry_rule", json=ENTRY_RULE)
    client.put("/api/rules/exit_rule", json=EXIT_RULE)
    client.put("/api/strategies/smoke_strategy", json=STRATEGY_BODY)


def test_run_backtest_returns_metrics_equity_curve_and_trades(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)

    resp = client.post(
        "/api/backtests",
        json={
            "strategy_id": "smoke_strategy",
            "symbols": ["005930"],
            "start": "2024-01-02",
            "end": "2024-12-31",
            "data_source": "fixture",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert "total_return" in body["metrics"]
    assert "mdd" in body["metrics"]

    assert "005930" in body["per_symbol"]
    assert "005930" in body["results"]

    equity_curve = body["results"]["005930"]["equity_curve"]
    assert isinstance(equity_curve, list)
    assert equity_curve
    assert set(equity_curve[0].keys()) == {"date", "value"}

    trades = body["results"]["005930"]["trades"]
    assert isinstance(trades, list)
    if trades:  # 신호 발생 여부는 데이터 의존적이므로 형상만 검증
        assert "entry_timestamp" in trades[0]
        assert "pnl" in trades[0]


def test_run_backtest_unknown_strategy_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.post(
        "/api/backtests",
        json={"strategy_id": "no_such", "symbols": ["005930"], "data_source": "fixture"},
    )
    assert resp.status_code == 404
    assert "등록된 항목 없음" in resp.json()["detail"]


def test_run_backtest_draft_strategy_rejected_with_409(tmp_path) -> None:
    client = _client(tmp_path)
    draft = {**STRATEGY_BODY, "rule": None}
    client.put("/api/strategies/draft_strategy", json=draft)

    resp = client.post(
        "/api/backtests",
        json={"strategy_id": "draft_strategy", "symbols": ["005930"], "data_source": "fixture"},
    )
    assert resp.status_code == 409


def test_run_backtest_no_symbols_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)  # universe.symbols == [], watchlist도 없음(tmp_path 격리)

    resp = client.post(
        "/api/backtests",
        json={"strategy_id": "smoke_strategy", "data_source": "fixture"},
    )
    assert resp.status_code == 404
    assert "대상 종목이 없습니다" in resp.json()["detail"]
