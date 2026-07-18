from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends

from quant_krx.config.settings import Settings, get_settings
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
