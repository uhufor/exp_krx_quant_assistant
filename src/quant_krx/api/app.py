from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from quant_krx.api.errors import register_error_handlers
from quant_krx.api.routers import backtests, factors, formulas, rules, strategies, templates

# src/quant_krx/api/app.py -> parents[3] == 저장소 루트(web/dist가 위치하는 곳)
_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app() -> FastAPI:
    """로컬 1인용 GUI API 팩토리(PRD 제약: localhost 전용, 인증 불필요)."""
    app = FastAPI(title="quant-krx GUI API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],  # vite dev server
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(factors.router, prefix="/api/factors", tags=["factors"])
    app.include_router(formulas.router, prefix="/api/formulas", tags=["formulas"])
    app.include_router(rules.router, prefix="/api/rules", tags=["rules"])
    app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
    app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
    app.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])

    # 프로덕션 빌드(web/dist)가 있으면 정적 파일로 서빙(SPA 라우팅 대응 html=True).
    # /api/* 라우터를 모두 등록한 뒤 마지막에 "/" 마운트해야 API 경로가 우선 매칭된다.
    # 빌드가 없으면(dev 모드) 조용히 건너뛴다 — vite dev server(:5173)가 프론트를 담당.
    if _WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")

    return app
