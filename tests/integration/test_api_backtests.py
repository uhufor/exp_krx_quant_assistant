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

    # GUI 자산곡선에 주가를 겹쳐 보여주기 위한 종가 곡선(price_curve) — 자산곡선과
    # 동일 형상([{date, value}])이며 같은 기간만큼 채워진다.
    price_curve = body["results"]["005930"]["price_curve"]
    assert isinstance(price_curve, list)
    assert price_curve
    assert set(price_curve[0].keys()) == {"date", "value"}

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


def test_run_backtest_symbol_not_in_fixture_returns_404_not_500(tmp_path) -> None:
    """fixture에 없는 유일한 종목 요청 시 vectorbt zero-size 크래시(500) 대신 명확한 404."""
    client = _client(tmp_path)
    _seed_runnable_strategy(client)

    resp = client.post(
        "/api/backtests",
        json={"strategy_id": "smoke_strategy", "symbols": ["035720"], "data_source": "fixture"},
    )
    assert resp.status_code == 404
    assert "035720" in resp.json()["detail"]
    assert "OHLCV" in resp.json()["detail"]


def test_run_backtest_partial_symbol_failure_isolated(tmp_path) -> None:
    """일부 종목만 데이터가 없을 때 배치 전체가 아니라 해당 종목만 errors로 격리된다(FR-17)."""
    client = _client(tmp_path)
    _seed_runnable_strategy(client)

    resp = client.post(
        "/api/backtests",
        json={
            "strategy_id": "smoke_strategy",
            "symbols": ["005930", "035720"],
            "start": "2024-01-02",
            "end": "2024-12-31",
            "data_source": "fixture",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert "005930" in body["results"]
    assert "035720" not in body["results"]
    assert "035720" in body["errors"]
    assert "OHLCV" in body["errors"]["035720"]


def test_run_backtest_no_symbols_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)  # universe.symbols == [], watchlist도 없음(tmp_path 격리)

    resp = client.post(
        "/api/backtests",
        json={"strategy_id": "smoke_strategy", "data_source": "fixture"},
    )
    assert resp.status_code == 404
    assert "대상 종목이 없습니다" in resp.json()["detail"]


# --- 실행 이력·캐시 API (P3) ---

_RUN_BODY = {
    "strategy_id": "smoke_strategy",
    "symbols": ["005930"],
    "start": "2024-01-02",
    "end": "2024-12-31",
    "data_source": "fixture",
}


def test_run_backtest_reports_run_id_and_cache_flag(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)

    first = client.post("/api/backtests", json=_RUN_BODY).json()
    assert first["run_id"]
    assert first["from_cache"] is False
    assert first["executed_at"]

    second = client.post("/api/backtests", json=_RUN_BODY).json()
    assert second["from_cache"] is True
    assert second["run_id"] == first["run_id"]


def test_run_backtest_use_cache_false_forces_new_run(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)

    first = client.post("/api/backtests", json=_RUN_BODY).json()
    second = client.post("/api/backtests", json={**_RUN_BODY, "use_cache": False}).json()

    assert second["from_cache"] is False
    assert second["run_id"] != first["run_id"]


def test_list_backtest_runs_returns_summaries_without_curves(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)
    client.post("/api/backtests", json=_RUN_BODY)

    resp = client.get("/api/backtests/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["strategy_id"] == "smoke_strategy"
    assert runs[0]["params"]["data_source"] == "fixture"
    assert "equity_curves" not in runs[0], "목록 응답은 곡선 데이터를 싣지 않는다"


def test_list_backtest_runs_filters_by_strategy(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)
    client.post("/api/backtests", json=_RUN_BODY)

    assert len(client.get("/api/backtests/runs?strategy_id=smoke_strategy").json()) == 1
    assert client.get("/api/backtests/runs?strategy_id=other").json() == []


def test_get_backtest_run_returns_equity_curves(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)
    run_id = client.post("/api/backtests", json=_RUN_BODY).json()["run_id"]

    resp = client.get(f"/api/backtests/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    curves = body["equity_curves"]["005930"]
    assert curves["equity"]
    assert set(curves["equity"][0].keys()) == {"date", "value"}


def test_get_backtest_run_missing_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)
    assert client.get("/api/backtests/runs/no-such-run").status_code == 404


def test_list_backtest_runs_on_fresh_db_returns_empty(tmp_path) -> None:
    """이력이 하나도 없는 최초 상태에서도 200 + 빈 목록이어야 한다(GUI 첫 진입 경로)."""
    client = _client(tmp_path)
    resp = client.get("/api/backtests/runs")
    assert resp.status_code == 200
    assert resp.json() == []


# --- 포트폴리오 모드 (P1) ---

PORTFOLIO_STRATEGY_BODY = {
    **STRATEGY_BODY,
    "portfolio": {
        "max_positions": 2,
        "rebalance": "monthly",
        "sizing": "equal_weight",
        "initial_cash": 10_000_000,
        "ranking": None,
    },
}
_PORTFOLIO_RUN_BODY = {
    "strategy_id": "pf_strategy",
    "symbols": ["005930", "000660", "006400"],
    "start": "2024-01-02",
    "end": "2024-12-18",
    "data_source": "fixture",
}


def _seed_portfolio_strategy(client: TestClient) -> None:
    client.put("/api/rules/entry_rule", json=ENTRY_RULE)
    client.put("/api/rules/exit_rule", json=EXIT_RULE)
    resp = client.put("/api/strategies/pf_strategy", json=PORTFOLIO_STRATEGY_BODY)
    assert resp.status_code in (200, 201), resp.text


def test_portfolio_strategy_roundtrips_through_api(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_portfolio_strategy(client)

    body = client.get("/api/strategies/pf_strategy").json()
    assert body["portfolio"]["max_positions"] == 2
    assert body["portfolio"]["rebalance"] == "monthly"


def test_portfolio_backtest_returns_portfolio_shape(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_portfolio_strategy(client)

    body = client.post("/api/backtests", json=_PORTFOLIO_RUN_BODY).json()

    assert body["is_portfolio"] is True
    assert body["per_symbol"] == {}, "자본 공유 모드에는 종목별 독립 성과가 없다"
    assert list(body["results"]) == ["__portfolio__"]
    assert body["weights"], "리밸런싱 배분이 응답에 포함되어야 한다"
    for allocation in body["weights"].values():
        assert len(allocation) <= 2


def test_portfolio_run_history_preserves_mode(tmp_path) -> None:
    """캐시로 복원해도 포트폴리오 모드와 배분이 유지되어야 한다."""
    client = _client(tmp_path)
    _seed_portfolio_strategy(client)

    first = client.post("/api/backtests", json=_PORTFOLIO_RUN_BODY).json()
    cached = client.post("/api/backtests", json=_PORTFOLIO_RUN_BODY).json()

    assert cached["from_cache"] is True
    assert cached["is_portfolio"] is True
    assert cached["weights"] == first["weights"]

    listed = client.get("/api/backtests/runs?strategy_id=pf_strategy").json()
    assert listed[0]["is_portfolio"] is True
    assert listed[0]["weights"] == first["weights"]


def test_portfolio_policy_change_invalidates_cache(tmp_path) -> None:
    """정책만 바꿔도 정의 지문이 달라져 재계산되어야 한다."""
    client = _client(tmp_path)
    _seed_portfolio_strategy(client)
    first = client.post("/api/backtests", json=_PORTFOLIO_RUN_BODY).json()

    changed = {
        **PORTFOLIO_STRATEGY_BODY,
        "portfolio": {**PORTFOLIO_STRATEGY_BODY["portfolio"], "max_positions": 3},
    }
    client.put("/api/strategies/pf_strategy", json=changed)
    second = client.post("/api/backtests", json=_PORTFOLIO_RUN_BODY).json()

    assert second["from_cache"] is False
    assert second["run_id"] != first["run_id"]


def test_invalid_portfolio_policy_rejected(tmp_path) -> None:
    client = _client(tmp_path)
    client.put("/api/rules/entry_rule", json=ENTRY_RULE)
    client.put("/api/rules/exit_rule", json=EXIT_RULE)

    bad = {
        **STRATEGY_BODY,
        "portfolio": {"max_positions": 0, "rebalance": "monthly",
                      "sizing": "equal_weight", "initial_cash": 1000, "ranking": None},
    }
    resp = client.put("/api/strategies/bad_pf", json=bad)
    assert resp.status_code >= 400
