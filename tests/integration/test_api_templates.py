from __future__ import annotations

from fastapi.testclient import TestClient

from quant_krx.api.app import create_app
from quant_krx.api.deps import get_db
from quant_krx.storage.db import Database


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


def test_list_templates_includes_builtin(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    body = resp.json()
    ids = {t["template_id"] for t in body}
    assert "ma_crossover" in ids
    assert all(t["origin"] in ("builtin", "user") for t in body)


def test_create_from_template_produces_runnable_strategy(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.post("/api/templates/from/ma_crossover", json={"new_id": "my_ma"})
    assert resp.status_code == 201
    assert resp.json()["id"] == "my_ma"

    resp = client.get("/api/strategies/my_ma")
    assert resp.status_code == 200

    resp = client.post("/api/strategies/my_ma/activate")
    assert resp.status_code == 200


def test_save_as_template_and_delete(tmp_path) -> None:
    client = _client(tmp_path)
    client.post("/api/templates/from/ma_crossover", json={"new_id": "my_ma"})

    resp = client.post(
        "/api/templates", json={"strategy_id": "my_ma", "template_id": "my_template"}
    )
    assert resp.status_code == 201

    resp = client.get("/api/templates")
    ids = {t["template_id"] for t in resp.json()}
    assert "my_template" in ids

    resp = client.delete("/api/templates/my_template")
    assert resp.status_code == 204


def test_delete_builtin_template_rejected(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.delete("/api/templates/ma_crossover")
    assert resp.status_code == 409
