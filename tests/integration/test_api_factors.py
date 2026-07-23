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


def test_list_factors_returns_catalog(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/factors")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 35  # 32종 + trading_value/volume/rolling_high(EPIC-03 노코드 스크리닝)
    ids = {item["id"] for item in body}
    assert "sma" in ids
    assert "per" in ids


def test_list_factors_filters_by_category(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/factors", params={"category": "value"})
    assert resp.status_code == 200
    body = resp.json()
    assert body
    assert all(item["category"] == "value" for item in body)


def test_get_factor_returns_metadata_and_resolved_params(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/factors/sma")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["id"] == "sma"
    assert "window" in body["resolved_params"]


def test_get_factor_unknown_id_returns_404_with_hint(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/factors/no_such_factor")
    assert resp.status_code == 404
    assert "사용 가능한 id" in resp.json()["detail"]
