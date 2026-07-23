from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends

from quant_krx.config.settings import Settings, get_settings
from quant_krx.data.base import DataProvider
from quant_krx.screening.service import ScreeningService
from quant_krx.storage.db import Database
from quant_krx.workspace.service import WorkspaceService


def get_db(settings: Settings = Depends(get_settings)) -> Iterator[Database]:
    """요청 스코프 Database.

    매 요청마다 열고 응답 후 닫는다(DuckDB 커넥션 비-스레드세이프, TR-GUI-012).
    """
    db = Database(settings.duckdb_path)
    db.connect()
    try:
        yield db
    finally:
        db.close()


def get_workspace_service(db: Database = Depends(get_db)) -> WorkspaceService:
    return WorkspaceService(db)


def get_data_provider(settings: Settings = Depends(get_settings)) -> DataProvider:
    """settings.provider.primary("fdr"|"pykrx")로 OHLCV 어댑터를 선택한다.

    무거운 provider는 lazy import(_ohlcv_provider_for와 동일 관례). 테스트는 이 의존성을
    dependency_overrides로 FixtureAdapter로 치환한다(TestClient 오프라인 실행).
    """
    if settings.provider.primary == "pykrx":
        from quant_krx.data.pykrx_adapter import PyKrxAdapter

        return PyKrxAdapter()
    from quant_krx.data.fdr_adapter import FDRAdapter

    return FDRAdapter()


def get_screening_service(
    db: Database = Depends(get_db), provider: DataProvider = Depends(get_data_provider)
) -> ScreeningService:
    return ScreeningService(db, provider)
