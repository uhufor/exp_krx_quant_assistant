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
        "left": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 5}},
        "operator": ">",
        "right": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 20}},
    },
}
STRATEGY_BODY = {
    "name": "검증 테스트 전략",
    "version": "1",
    "factor_refs": [
        {"factor_id": "sma", "params": {"window": 5}},
        {"factor_id": "sma", "params": {"window": 20}},
    ],
    "universe": {"symbols": []},
    "rule": {"roles": {"entry": ["entry_rule"]}},
}
PERIOD = {"start": "2024-01-02", "end": "2024-12-18"}


def _client(tmp_path) -> TestClient:
    app = create_app()
    test_settings = Settings(
        duckdb_path=str(tmp_path / "test.duckdb"),
        watchlist_path=str(tmp_path / "no_such_watchlist.yaml"),
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


def _seed(client: TestClient) -> None:
    client.put("/api/rules/entry_rule", json=ENTRY_RULE)
    client.put("/api/strategies/val_strategy", json=STRATEGY_BODY)


def _post(client: TestClient, **extra):
    return client.post(
        "/api/validations",
        json={
            "strategy_id": "val_strategy", "symbols": ["005930"],
            "data_source": "fixture", **PERIOD, **extra,
        },
    )


def test_run_validation_returns_summary_and_folds(tmp_path) -> None:
    client = _client(tmp_path)
    _seed(client)

    resp = _post(client, mode="holdout")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["strategy_id"] == "val_strategy"
    assert len(body["folds"]) == 1
    assert body["summary"]["folds_total"] == 1
    assert "degradation" in body["summary"]

    fold = body["folds"][0]
    assert set(fold["fold"]) == {"index", "train_start", "train_end", "test_start", "test_end"}
    assert fold["train_metrics"] is not None
    assert fold["test_metrics"] is not None


def test_oos_equity_uses_the_shared_curve_contract(tmp_path) -> None:
    """저장 포맷·백테스트 응답과 같은 [{date, value}] 형상이어야 GUI가 곡선을 공유할 수 있다."""
    client = _client(tmp_path)
    _seed(client)

    body = _post(client, mode="holdout").json()
    curve = body["oos_equity"]
    assert curve
    assert set(curve[0].keys()) == {"date", "value"}


def test_walkforward_produces_multiple_folds(tmp_path) -> None:
    client = _client(tmp_path)
    _seed(client)

    body = _post(client, n_folds=2, test_ratio=0.4).json()
    assert len(body["folds"]) == 2
    assert [f["fold"]["index"] for f in body["folds"]] == [0, 1]


def test_grid_records_every_candidate(tmp_path) -> None:
    client = _client(tmp_path)
    _seed(client)

    body = _post(client, mode="holdout", grid={"factor.sma@5.window": [3, 5]}).json()
    fold = body["folds"][0]
    assert len(fold["candidates"]) == 2
    assert fold["params"]["factor.sma@5.window"] in (3, 5)


def test_run_is_listable_and_retrievable(tmp_path) -> None:
    client = _client(tmp_path)
    _seed(client)
    validation_id = _post(client, mode="holdout").json()["validation_id"]

    listed = client.get("/api/validations")
    assert listed.status_code == 200
    assert [r["validation_id"] for r in listed.json()] == [validation_id]

    detail = client.get(f"/api/validations/{validation_id}")
    assert detail.status_code == 200
    assert detail.json()["summary"] == listed.json()[0]["summary"]
    assert detail.json()["params"]["data_source"] == "fixture"


def test_list_filters_by_strategy(tmp_path) -> None:
    client = _client(tmp_path)
    _seed(client)
    _post(client, mode="holdout")

    assert client.get("/api/validations", params={"strategy_id": "other"}).json() == []
    assert len(client.get("/api/validations", params={"strategy_id": "val_strategy"}).json()) == 1


def test_unknown_strategy_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.post(
        "/api/validations",
        json={"strategy_id": "no_such", "symbols": ["005930"], "data_source": "fixture"},
    )
    assert resp.status_code == 404


def test_unknown_validation_id_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/validations/nope").status_code == 404


def test_impossible_fold_split_returns_409_not_500(tmp_path) -> None:
    """폴드 분할 실패는 사용자 입력 문제이므로 서버 오류로 나가면 안 된다."""
    client = _client(tmp_path)
    _seed(client)

    resp = _post(client, n_folds=30)
    assert resp.status_code == 409, resp.text
    assert "검증 구간" in resp.json()["detail"]


def test_unknown_objective_is_rejected_by_schema(tmp_path) -> None:
    client = _client(tmp_path)
    _seed(client)
    assert _post(client, objective="omega").status_code == 422
