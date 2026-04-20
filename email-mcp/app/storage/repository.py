from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import ApprovalRecord, Draft, DraftStatus, DraftVersion, SendRecord


def _fingerprint(subject: str, body: str, to: list[str], cc: list[str], bcc: list[str]) -> str:
    payload = json.dumps(
        {"subject": subject, "body": body, "to": to, "cc": cc, "bcc": bcc},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DraftRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create_draft(
        self,
        *,
        thread_id: str,
        subject: str,
        body: str,
        to_addresses: list[str],
        cc_addresses: list[str],
        bcc_addresses: list[str],
        version_source: str,
    ) -> Draft:
        d = Draft(thread_id=thread_id, status=DraftStatus.PROPOSED)
        self._s.add(d)
        self._s.flush()
        v = DraftVersion(
            draft_id=d.id,
            version_no=1,
            source=version_source,
            subject=subject,
            body=body,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
        )
        self._s.add(v)
        self._s.flush()
        return d

    def set_status(self, draft: Draft, status: DraftStatus) -> None:
        draft.status = status.value
        draft.updated_at = datetime.now(timezone.utc)

    def add_human_version(
        self,
        draft: Draft,
        *,
        subject: str,
        body: str,
        to_addresses: list[str],
        cc_addresses: list[str],
        bcc_addresses: list[str],
    ) -> DraftVersion:
        next_no = max((v.version_no for v in draft.versions), default=0) + 1
        v = DraftVersion(
            draft_id=draft.id,
            version_no=next_no,
            source="human",
            subject=subject,
            body=body,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
        )
        self._s.add(v)
        self._s.flush()
        return v

    def record_approval(
        self,
        draft: Draft,
        *,
        approver_id: str,
        subject: str,
        body: str,
        to_addresses: list[str],
        cc_addresses: list[str],
        bcc_addresses: list[str],
    ) -> ApprovalRecord:
        fp = _fingerprint(subject, body, to_addresses, cc_addresses, bcc_addresses)
        a = ApprovalRecord(draft_id=draft.id, approver_id=approver_id, payload_fingerprint=fp)
        self._s.add(a)
        self._s.flush()
        return a

    def record_send(self, draft: Draft, *, provider_message_id: str | None) -> SendRecord:
        s = SendRecord(draft_id=draft.id, provider_message_id=provider_message_id)
        self._s.add(s)
        self._s.flush()
        return s

    def get_by_thread_id(self, thread_id: str) -> Draft | None:
        return self._s.execute(select(Draft).where(Draft.thread_id == thread_id)).scalar_one_or_none()
