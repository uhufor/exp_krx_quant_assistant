from __future__ import annotations

from fastapi.testclient import TestClient

from quant_krx.api.app import create_app
from quant_krx.api.deps import get_db
from quant_krx.storage.db import Database

VALID_FORMULA_BODY = {
    "name": "PER 프리미엄 갭",
    "version": "1",
    "expression": {
        "node": "binary",
        "op": "-",
        "left": {"kind": "factor", "factor_id": "per", "column": "per", "params": {}},
        "right": {"kind": "constant", "value": 10},
    },
    "output_column": "value",
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


def test_formula_crud_roundtrip(tmp_path) -> None:
    client = _client(tmp_path)

    resp = client.put("/api/formulas/per_gap", json=VALID_FORMULA_BODY)
    assert resp.status_code == 200
    assert resp.json()["id"] == "per_gap"

    resp = client.get("/api/formulas/per_gap")
    assert resp.status_code == 200
    assert resp.json()["name"] == "PER 프리미엄 갭"

    resp = client.get("/api/formulas")
    assert resp.status_code == 200
    assert any(f["id"] == "per_gap" for f in resp.json())

    resp = client.delete("/api/formulas/per_gap")
    assert resp.status_code == 204

    resp = client.get("/api/formulas/per_gap")
    assert resp.status_code == 404
    assert "등록된 항목 없음" in resp.json()["detail"]


def test_formula_validate_draft_reports_errors(tmp_path) -> None:
    client = _client(tmp_path)
    bad_body = {
        **VALID_FORMULA_BODY,
        "expression": {
            "node": "binary",
            "op": "-",
            "left": {"kind": "factor", "factor_id": "no_such_factor", "column": "x", "params": {}},
            "right": {"kind": "constant", "value": 10},
        },
    }
    resp = client.post("/api/formulas/validate", json=bad_body)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"]


def test_formula_validate_draft_ok(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.post("/api/formulas/validate", json=VALID_FORMULA_BODY)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "errors": []}


def test_formula_upsert_missing_field_returns_400(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.put("/api/formulas/broken", json={"name": "x"})  # version/expression 누락
    assert resp.status_code == 400
    assert "필수 필드 누락" in resp.json()["detail"]
