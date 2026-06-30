from __future__ import annotations

import logging

from quant_krx.storage.db import Database

logger = logging.getLogger(__name__)


class OutboxManager:
    """notification_outbox 관리 유틸리티."""

    def __init__(self, db: Database):
        self._db = db

    def get_pending(self, channel: str | None = None):
        return self._db.get_pending_notifications(channel)

    def retry_all(self, notifier) -> dict[str, list[str]]:
        """모든 채널의 pending 알림을 재시도."""
        return {"telegram": notifier.retry_pending()}
