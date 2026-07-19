from __future__ import annotations

from fastapi.testclient import TestClient

from quant_krx.api.app import create_app
from quant_krx.api.deps import get_db
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

    def _override_get_db():
        db = Database(path=tmp_path / "test.duckdb")
        db.connect()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _seed_runnable_strategy(client: TestClient, strategy_id: str = "smoke_strategy") -> None:
    assert client.put("/api/rules/entry_rule", json=ENTRY_RULE).status_code == 200
    assert client.put("/api/rules/exit_rule", json=EXIT_RULE).status_code == 200
    resp = client.put(f"/api/strategies/{strategy_id}", json=STRATEGY_BODY)
    assert resp.status_code == 200


def test_strategy_crud_roundtrip(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)

    resp = client.get("/api/strategies/smoke_strategy")
    assert resp.status_code == 200
    assert resp.json()["rule"]["roles"]["entry"] == ["entry_rule"]

    resp = client.get("/api/strategies")
    assert any(s["id"] == "smoke_strategy" for s in resp.json())

    resp = client.delete("/api/strategies/smoke_strategy")
    assert resp.status_code == 204
    assert client.get("/api/strategies/smoke_strategy").status_code == 404


def test_strategy_validate_draft(tmp_path) -> None:
    client = _client(tmp_path)
    client.put("/api/rules/entry_rule", json=ENTRY_RULE)
    client.put("/api/rules/exit_rule", json=EXIT_RULE)

    resp = client.post("/api/strategies/validate", json=STRATEGY_BODY)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "errors": []}


def test_strategy_activate_deactivate_and_list_active(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)

    resp = client.post("/api/strategies/smoke_strategy/activate")
    assert resp.status_code == 200
    assert resp.json() == {"active": True}

    resp = client.get("/api/strategies/active")
    assert resp.json() == ["smoke_strategy"]

    resp = client.post("/api/strategies/smoke_strategy/deactivate")
    assert resp.status_code == 200
    assert client.get("/api/strategies/active").json() == []


def test_strategy_activate_draft_rejected_with_409(tmp_path) -> None:
    client = _client(tmp_path)
    draft = {**STRATEGY_BODY, "rule": None}
    client.put("/api/strategies/draft_strategy", json=draft)

    resp = client.post("/api/strategies/draft_strategy/activate")
    assert resp.status_code == 409


def test_strategy_export_import_roundtrip(tmp_path) -> None:
    client = _client(tmp_path)
    _seed_runnable_strategy(client)

    resp = client.get("/api/strategies/smoke_strategy/export")
    assert resp.status_code == 200
    bundle = resp.json()
    assert bundle["strategy"]["id"] == "smoke_strategy"
    assert len(bundle["rules"]) == 2

    # 다른 격리 DB로 import 왕복 확인
    other_client = _client(tmp_path.parent / (tmp_path.name + "_other"))
    resp = other_client.post("/api/strategies/import", json=bundle)
    assert resp.status_code == 201
    assert resp.json() == {"strategy_id": "smoke_strategy"}
    assert other_client.get("/api/strategies/smoke_strategy").status_code == 200


def test_strategy_upsert_missing_field_returns_400(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.put("/api/strategies/broken", json={"name": "x"})
    assert resp.status_code == 400
    assert "필수 필드 누락" in resp.json()["detail"]
