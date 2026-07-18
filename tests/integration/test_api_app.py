from __future__ import annotations

from fastapi.testclient import TestClient

import quant_krx.api.app as app_module
from quant_krx.api.app import create_app


def test_root_serves_frontend_build_when_dist_exists(tmp_path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>quant-krx GUI</body></html>")
    monkeypatch.setattr(app_module, "_WEB_DIST", dist)

    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "quant-krx GUI" in resp.text

    # /api/* 라우터가 정적 마운트("/")보다 우선 매칭되어야 한다(app.py 등록 순서 의존).
    resp = client.get("/api/factors")
    assert resp.status_code == 200


def test_root_returns_404_when_dist_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_WEB_DIST", tmp_path / "no_such_dist")

    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 404

    resp = client.get("/api/factors")
    assert resp.status_code == 200
