from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import TrackedSend


class TrackedSendRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(
        self,
        *,
        draft_id: str | None,
        workflow_thread_id: str,
        gmail_thread_id: str | None,
        gmail_message_id: str,
        to_addresses: list[str],
        cc_addresses: list[str],
        mailbox_address: str,
        sent_at: datetime,
        sla_deadline_at: datetime,
    ) -> TrackedSend:
        row = TrackedSend(
            draft_id=draft_id,
            workflow_thread_id=workflow_thread_id,
            gmail_thread_id=gmail_thread_id,
            gmail_message_id=gmail_message_id,
            to_addresses=list(to_addresses),
            cc_addresses=list(cc_addresses),
            mailbox_address=mailbox_address,
            sent_at=sent_at,
            sla_deadline_at=sla_deadline_at,
            status="awaiting_reply",
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get(self, track_id: str) -> TrackedSend | None:
        return self._s.get(TrackedSend, track_id)

    def list_recent(self, *, limit: int = 50) -> list[TrackedSend]:
        stmt = select(TrackedSend).order_by(TrackedSend.sent_at.desc()).limit(limit)
        return list(self._s.scalars(stmt).all())

    def set_gmail_thread_id(self, row: TrackedSend, gmail_thread_id: str) -> None:
        row.gmail_thread_id = gmail_thread_id

    def update_check(
        self,
        row: TrackedSend,
        *,
        status: str,
        reply_gmail_message_id: str | None = None,
        reply_from: str | None = None,
        last_error: str | None = None,
        clear_last_error: bool = False,
        gmail_thread_id: str | None = None,
        touch_checked_at: bool = True,
    ) -> None:
        row.status = status
        if touch_checked_at:
            row.last_checked_at = datetime.now(timezone.utc)
        if reply_gmail_message_id is not None:
            row.reply_gmail_message_id = reply_gmail_message_id
        if reply_from is not None:
            row.reply_from = reply_from
        if clear_last_error:
            row.last_error = None
        elif last_error is not None:
            row.last_error = last_error
        if gmail_thread_id is not None:
            row.gmail_thread_id = gmail_thread_id
