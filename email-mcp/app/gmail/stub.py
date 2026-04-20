from __future__ import annotations

import time
import uuid

from app.config import Settings


class StubGmailClient:
    """In-memory threads for Phase 1–4 tests; supports reply detection via `add_inbound_reply`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._threads: dict[str, list[dict]] = {}
        self._msg_to_thread: dict[str, str] = {}

    def _mailbox(self) -> str:
        if self._settings and self._settings.mailbox_address:
            return self._settings.mailbox_address
        return "sender@stub.griddynamics.com"

    def send_message(
        self,
        *,
        subject: str,
        body: str,
        to: list[str],
        cc: list[str],
        bcc: list[str],
    ) -> str:
        tid = str(uuid.uuid4())
        mid = f"stub:{uuid.uuid4()}"
        now = int(time.time() * 1000)
        headers = [
            {"name": "From", "value": self._mailbox()},
            {"name": "To", "value": ", ".join(to)},
            {"name": "Subject", "value": subject},
        ]
        if cc:
            headers.append({"name": "Cc", "value": ", ".join(cc)})
        msg = {
            "id": mid,
            "threadId": tid,
            "internalDate": str(now),
            "snippet": body[:80],
            "payload": {"headers": headers},
        }
        self._threads.setdefault(tid, []).append(msg)
        self._msg_to_thread[mid] = tid
        return mid

    def get_message(self, message_id: str) -> dict:
        tid = self._msg_to_thread.get(message_id)
        if not tid:
            return {"id": message_id, "threadId": f"orphan-{message_id}"}
        return {"id": message_id, "threadId": tid}

    def get_thread(self, thread_id: str) -> dict:
        messages = list(self._threads.get(thread_id, []))
        return {"thread_id": thread_id, "messages": messages, "note": "stub Gmail client"}

    def resolve_mailbox_address(self) -> str:
        return self._mailbox()

    def add_inbound_reply(self, gmail_thread_id: str, from_email: str, *, snippet: str = "Thanks!") -> str:
        """Test helper: simulate a recipient reply in a stub thread."""
        now = int(time.time() * 1000) + 10
        mid = f"stub-reply:{uuid.uuid4()}"
        msg = {
            "id": mid,
            "threadId": gmail_thread_id,
            "internalDate": str(now),
            "snippet": snippet,
            "payload": {
                "headers": [
                    {"name": "From", "value": from_email},
                    {"name": "To", "value": self._mailbox()},
                ]
            },
        }
        self._threads.setdefault(gmail_thread_id, []).append(msg)
        self._msg_to_thread[mid] = gmail_thread_id
        return mid
