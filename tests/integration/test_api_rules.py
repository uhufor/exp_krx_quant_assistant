from __future__ import annotations

from fastapi.testclient import TestClient

from quant_krx.api.app import create_app
from quant_krx.api.deps import get_db
from quant_krx.storage.db import Database

VALID_RULE_BODY = {
    "name": "SMA 골든크로스",
    "version": "1",
    "root": {
        "node": "predicate",
        "left": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 20}},
        "operator": "crosses_above",
        "right": {"kind": "factor", "factor_id": "sma", "column": "sma", "params": {"window": 60}},
    },
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


def test_rule_crud_roundtrip(tmp_path) -> None:
    client = _client(tmp_path)

    resp = client.put("/api/rules/sma_golden_cross", json=VALID_RULE_BODY)
    assert resp.status_code == 200
    assert resp.json()["id"] == "sma_golden_cross"

    resp = client.get("/api/rules/sma_golden_cross")
    assert resp.status_code == 200
    assert resp.json()["root"]["operator"] == "crosses_above"

    resp = client.get("/api/rules")
    assert any(r["id"] == "sma_golden_cross" for r in resp.json())

    resp = client.delete("/api/rules/sma_golden_cross")
    assert resp.status_code == 204

    resp = client.get("/api/rules/sma_golden_cross")
    assert resp.status_code == 404


def test_rule_validate_draft_ok(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.post("/api/rules/validate", json=VALID_RULE_BODY)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "errors": []}


def test_rule_validate_draft_reports_unknown_factor(tmp_path) -> None:
    client = _client(tmp_path)
    bad_body = {
        **VALID_RULE_BODY,
        "root": {
            **VALID_RULE_BODY["root"],
            "left": {"kind": "factor", "factor_id": "no_such_factor", "column": "x", "params": {}},
        },
    }
    resp = client.post("/api/rules/validate", json=bad_body)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"]
