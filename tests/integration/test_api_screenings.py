from __future__ import annotations

from fastapi.testclient import TestClient

from quant_krx.api.app import create_app
from quant_krx.api.deps import get_data_provider, get_db
from quant_krx.data.fixture_adapter import FixtureAdapter
from quant_krx.storage.db import Database

PRICE_CONDITION_BODY = {
    "id": "price_gt",
    "name": "종가 20만 초과",
    "version": "1",
    "universe": {"market": "KRX", "exclusion_filters": []},
    "root": {
        "node": "predicate",
        "left": {"kind": "factor", "factor_id": "price", "column": "close", "params": {}},
        "operator": ">",
        "right": {"kind": "constant", "value": 200000},
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
    app.dependency_overrides[get_data_provider] = lambda: FixtureAdapter()
    return TestClient(app)


def test_screening_crud_roundtrip(tmp_path) -> None:
    client = _client(tmp_path)

    resp = client.post("/api/screenings", json=PRICE_CONDITION_BODY)
    assert resp.status_code == 201
    assert resp.json()["id"] == "price_gt"

    resp = client.get("/api/screenings/price_gt")
    assert resp.status_code == 200
    assert resp.json()["root"]["operator"] == ">"

    resp = client.get("/api/screenings")
    assert any(c["id"] == "price_gt" for c in resp.json())

    updated_body = {**PRICE_CONDITION_BODY, "name": "종가 20만 초과(수정)"}
    resp = client.put("/api/screenings/price_gt", json=updated_body)
    assert resp.status_code == 200
    assert resp.json()["name"] == "종가 20만 초과(수정)"

    resp = client.delete("/api/screenings/price_gt")
    assert resp.status_code == 204

    resp = client.get("/api/screenings/price_gt")
    assert resp.status_code == 404


def test_screening_get_unknown_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/screenings/no_such")
    assert resp.status_code == 404
    assert "등록된 항목 없음" in resp.json()["detail"]


def test_screening_validate_ok(tmp_path) -> None:
    client = _client(tmp_path)
    client.post("/api/screenings", json=PRICE_CONDITION_BODY)

    resp = client.post("/api/screenings/price_gt/validate")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "errors": []}


def test_screening_validate_reports_unknown_factor(tmp_path) -> None:
    client = _client(tmp_path)
    bad_body = {
        **PRICE_CONDITION_BODY,
        "id": "bad_factor",
        "root": {
            **PRICE_CONDITION_BODY["root"],
            "left": {"kind": "factor", "factor_id": "no_such_factor", "column": "x", "params": {}},
        },
    }
    client.post("/api/screenings", json=bad_body)

    resp = client.post("/api/screenings/bad_factor/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"]


def test_screening_validate_unknown_id_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.post("/api/screenings/no_such/validate")
    assert resp.status_code == 404


def test_screening_run_returns_passed_symbols(tmp_path) -> None:
    client = _client(tmp_path)
    client.post("/api/screenings", json=PRICE_CONDITION_BODY)

    resp = client.post("/api/screenings/price_gt/run", json={"as_of": "2024-12-18"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["condition_id"] == "price_gt"
    assert body["as_of"] == "2024-12-18"
    assert isinstance(body["passed"], list)
    assert body["count"] == len(body["passed"])
    if body["passed"]:
        assert set(body["passed"][0].keys()) == {"symbol", "name"}


def test_screening_run_unknown_id_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.post("/api/screenings/no_such/run", json={})
    assert resp.status_code == 404


def test_screening_universe_size_returns_count_without_running(tmp_path) -> None:
    client = _client(tmp_path)
    client.post("/api/screenings", json=PRICE_CONDITION_BODY)

    resp = client.get("/api/screenings/price_gt/universe-size")
    assert resp.status_code == 200
    body = resp.json()
    assert body["condition_id"] == "price_gt"
    assert body["count"] == 5  # FixtureAdapter 5종목, 제외 필터 없음


def test_screening_universe_size_unknown_id_returns_404(tmp_path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/screenings/no_such/universe-size")
    assert resp.status_code == 404


def test_screening_create_unsupported_filter_returns_400(tmp_path) -> None:
    client = _client(tmp_path)
    bad_body = {
        **PRICE_CONDITION_BODY,
        "id": "bad_universe",
        "universe": {"market": "KRX", "exclusion_filters": ["administrative_issue"]},
    }
    resp = client.post("/api/screenings", json=bad_body)
    assert resp.status_code == 400


def test_screening_create_missing_id_returns_400(tmp_path) -> None:
    client = _client(tmp_path)
    body = {k: v for k, v in PRICE_CONDITION_BODY.items() if k != "id"}
    resp = client.post("/api/screenings", json=body)
    assert resp.status_code == 400
