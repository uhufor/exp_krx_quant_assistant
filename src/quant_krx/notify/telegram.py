from __future__ import annotations

import hashlib
import logging

from quant_krx.storage.db import Database

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram Bot API를 통한 알림 발송."""

    def __init__(self, bot_token: str, chat_id: str, db: Database):
        self._token = bot_token
        self._chat_id = chat_id
        self._db = db

    def send(self, run_id: str, text: str, dry_run: bool = False) -> str:
        """
        텍스트 메시지 발송. durable outbox 경유.
        반환값: notification_id (dry_run=True 시 빈 문자열)
        """
        if dry_run:
            logger.info(f"[DRY-RUN] Telegram 발송 생략: run_id={run_id}")
            return ""

        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        nid = self._db.enqueue_notification(
            run_id=run_id,
            channel="telegram",
            content_hash=content_hash,
            payload=text,
        )

        # 이미 발송된 경우 스킵 (크래시 이후 재시작 시 중복 방지)
        if self._db.get_notification_status(nid) == "sent":
            logger.info(f"Telegram 이미 발송됨, 스킵: nid={nid}")
            return nid

        try:
            self._send_via_api(text)
            self._db.mark_notification_sent(nid)
            logger.info(f"Telegram 발송 성공: run_id={run_id}, nid={nid}")
        except Exception as e:
            self._db.mark_notification_failed(nid, str(e))
            logger.error(f"Telegram 발송 실패: {e}")
            raise

        return nid

    def retry_pending(self) -> list[str]:
        """pending 상태의 알림을 재시도. 성공한 notification_id 목록 반환."""
        pending = self._db.get_pending_notifications("telegram")
        succeeded = []
        for _, row in pending.iterrows():
            try:
                self._send_via_api(row["payload"])
                self._db.mark_notification_sent(row["id"])
                succeeded.append(row["id"])
            except Exception as e:
                self._db.mark_notification_failed(row["id"], str(e))
        return succeeded

    def _send_via_api(self, text: str) -> None:
        """실제 Telegram API 호출 (동기, urllib 사용)."""
        import json
        import urllib.parse
        import urllib.request

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        # 4096자 Telegram 제한: 줄 경계로 청크 분할
        chunks = self._split_on_lines(text, 4000)
        for chunk in chunks:
            data = urllib.parse.urlencode(
                {
                    "chat_id": self._chat_id,
                    "text": chunk,
                    "parse_mode": "Markdown",
                }
            ).encode()
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                if not result.get("ok"):
                    raise RuntimeError(f"Telegram API error: {result}")

    @staticmethod
    def _split_on_lines(text: str, max_len: int) -> list[str]:
        """Markdown 엔티티 손상 없이 줄 경계에서 청크 분할."""
        if len(text) <= max_len:
            return [text]
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in text.splitlines(keepends=True):
            if current_len + len(line) > max_len and current:
                chunks.append("".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line)
        if current:
            chunks.append("".join(current))
        return chunks
