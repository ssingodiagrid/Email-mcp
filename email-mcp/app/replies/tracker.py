from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.gmail.client import GmailClient
from app.replies.parse import message_header, parse_address_list
from app.storage.models import TrackedSend
from app.storage.tracking_repository import TrackedSendRepository


def _analyze_thread(
    thread: dict,
    *,
    sent_message_id: str,
    recipient_emails: set[str],
    mailbox_lower: str,
) -> dict:
    messages = thread.get("messages") or []
    sent_ts: int | None = None
    for m in messages:
        if m.get("id") == sent_message_id:
            raw = m.get("internalDate")
            sent_ts = int(raw) if raw is not None else None
            break
    if sent_ts is None:
        return {"replied": False, "reason": "sent_message_not_in_thread"}

    for m in messages:
        if m.get("id") == sent_message_id:
            continue
        raw = m.get("internalDate")
        ts = int(raw) if raw is not None else 0
        if ts <= sent_ts:
            continue
        from_h = message_header(m, "From")
        from_addrs = parse_address_list(from_h)
        if not from_addrs:
            continue
        if any(a in recipient_emails for a in from_addrs):
            return {
                "replied": True,
                "reply_message_id": m.get("id"),
                "reply_from": from_h,
            }
        if any(a != mailbox_lower for a in from_addrs):
            return {
                "replied": True,
                "reply_message_id": m.get("id"),
                "reply_from": from_h,
                "note": "reply_from_non_recipient",
            }
    return {"replied": False}


class ReplyTracker:
    def __init__(
        self,
        *,
        settings: Settings,
        gmail: GmailClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._settings = settings
        self._gmail = gmail
        self._sessions = session_factory

    def register_after_send(
        self,
        *,
        draft_id: str | None,
        workflow_thread_id: str,
        gmail_message_id: str,
        gmail_thread_id: str | None,
        to_addresses: list[str],
        cc_addresses: list[str],
        sent_at: datetime | None = None,
    ) -> str:
        sent_at = sent_at or datetime.now(timezone.utc)
        sla = sent_at + timedelta(hours=self._settings.reply_sla_hours)
        mailbox = self._gmail.resolve_mailbox_address()
        session = self._sessions()
        try:
            repo = TrackedSendRepository(session)
            row = repo.create(
                draft_id=draft_id,
                workflow_thread_id=workflow_thread_id,
                gmail_thread_id=gmail_thread_id,
                gmail_message_id=gmail_message_id,
                to_addresses=list(to_addresses),
                cc_addresses=list(cc_addresses),
                mailbox_address=mailbox,
                sent_at=sent_at,
                sla_deadline_at=sla,
            )
            session.commit()
            return row.id
        finally:
            session.close()

    def track_reply_status(self, track_id: str) -> dict:
        session = self._sessions()
        try:
            repo = TrackedSendRepository(session)
            row = repo.get(track_id)
            if row is None:
                return {"error": "unknown track_id"}
            if row.status in ("replied",):
                return self._snapshot(row)

            thread_id = row.gmail_thread_id
            if not thread_id:
                meta = self._safe_get_message(row.gmail_message_id)
                thread_id = (meta or {}).get("threadId")
                if thread_id:
                    repo.set_gmail_thread_id(row, str(thread_id))
                    session.commit()

            if not thread_id:
                repo.update_check(
                    row,
                    status="error",
                    last_error="missing gmail_thread_id and could not resolve from message",
                )
                session.commit()
                return self._snapshot(row)

            try:
                thread = self._gmail.get_thread(thread_id)
            except Exception as e:  # noqa: BLE001
                repo.update_check(row, status="error", last_error=str(e))
                session.commit()
                return self._snapshot(row)

            rec = {e.lower() for e in row.to_addresses + row.cc_addresses}
            analysis = _analyze_thread(
                thread,
                sent_message_id=row.gmail_message_id,
                recipient_emails=rec,
                mailbox_lower=row.mailbox_address.lower(),
            )
            if analysis.get("replied"):
                repo.update_check(
                    row,
                    status="replied",
                    reply_gmail_message_id=str(analysis.get("reply_message_id") or ""),
                    reply_from=analysis.get("reply_from"),
                    clear_last_error=True,
                )
            else:
                repo.update_check(row, status="awaiting_reply", clear_last_error=True)
            session.commit()
            return self._snapshot(row)
        finally:
            session.close()

    def detect_no_response(self, track_id: str) -> dict:
        snap = self.track_reply_status(track_id)
        if snap.get("error"):
            return snap
        session = self._sessions()
        try:
            repo = TrackedSendRepository(session)
            row = repo.get(track_id)
            if row is None:
                return {"error": "unknown track_id"}
            now = datetime.now(timezone.utc)
            deadline = row.sla_deadline_at
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            overdue = now > deadline
            if row.status == "awaiting_reply" and overdue:
                repo.update_check(row, status="no_response")
                session.commit()
            row = repo.get(track_id)
            assert row is not None
            return {
                **self._snapshot(row),
                "sla_deadline_at": deadline.isoformat(),
                "now": now.isoformat(),
                "overdue": overdue,
                "no_response": row.status == "no_response",
            }
        finally:
            session.close()

    def list_tracked_sends(self, *, limit: int = 50) -> dict:
        session = self._sessions()
        try:
            repo = TrackedSendRepository(session)
            rows = repo.list_recent(limit=limit)
            return {"items": [self._snapshot(r) for r in rows]}
        finally:
            session.close()

    def _safe_get_message(self, message_id: str) -> dict | None:
        try:
            return self._gmail.get_message(message_id)
        except Exception:  # noqa: BLE001
            return None

    def _snapshot(self, row: TrackedSend) -> dict:
        r = row
        return {
            "track_id": r.id,
            "draft_id": r.draft_id,
            "workflow_thread_id": r.workflow_thread_id,
            "gmail_thread_id": r.gmail_thread_id,
            "gmail_message_id": r.gmail_message_id,
            "status": r.status,
            "sent_at": r.sent_at.isoformat(),
            "sla_deadline_at": r.sla_deadline_at.isoformat(),
            "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
            "reply_gmail_message_id": r.reply_gmail_message_id,
            "reply_from": r.reply_from,
            "last_error": r.last_error,
            "to_addresses": list(r.to_addresses),
            "cc_addresses": list(r.cc_addresses),
        }
