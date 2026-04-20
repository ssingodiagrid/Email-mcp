from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import Settings


class RealGmailClient:
    """Gmail API v1 wrapper: send + read thread (Phase 2)."""

    def __init__(self, settings: Settings, credentials: Credentials) -> None:
        self._settings = settings
        self._creds = credentials
        self._service: Any = None

    def _ensure_fresh_credentials(self) -> None:
        if not self._creds.valid:
            self._creds.refresh(Request())

    def _api(self):
        self._ensure_fresh_credentials()
        if self._service is None:
            self._service = build("gmail", "v1", credentials=self._creds, cache_discovery=False)
        return self._service

    @staticmethod
    def _encode_raw_message(msg: EmailMessage) -> dict[str, str]:
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        return {"raw": raw}

    def send_message(
        self,
        *,
        subject: str,
        body: str,
        to: list[str],
        cc: list[str],
        bcc: list[str],
    ) -> str:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg.set_content(body)
        user = self._settings.gmail_user_id
        try:
            sent = (
                self._api()
                .users()
                .messages()
                .send(userId=user, body=self._encode_raw_message(msg))
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"Gmail send failed: {e}") from e
        mid = sent.get("id")
        if not mid:
            raise RuntimeError("Gmail send returned no message id")
        return str(mid)

    def get_thread(self, thread_id: str) -> dict:
        user = self._settings.gmail_user_id
        try:
            raw = (
                self._api()
                .users()
                .threads()
                .get(userId=user, id=thread_id, format="full")
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"Gmail thread fetch failed: {e}") from e
        messages_out: list[dict] = []
        for m in raw.get("messages") or []:
            messages_out.append(
                {
                    "id": m.get("id"),
                    "threadId": m.get("threadId"),
                    "snippet": m.get("snippet"),
                    "internalDate": m.get("internalDate"),
                    "labelIds": m.get("labelIds"),
                    "payload": m.get("payload"),
                }
            )
        return {
            "thread_id": raw.get("id", thread_id),
            "history_id": raw.get("historyId"),
            "messages": messages_out,
        }

    def get_message(self, message_id: str) -> dict:
        user = self._settings.gmail_user_id
        try:
            return (
                self._api()
                .users()
                .messages()
                .get(userId=user, id=message_id, format="full")
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"Gmail message fetch failed: {e}") from e

    def resolve_mailbox_address(self) -> str:
        if self._settings.mailbox_address:
            return self._settings.mailbox_address
        user = self._settings.gmail_user_id
        try:
            prof = self._api().users().getProfile(userId=user).execute()
            em = prof.get("emailAddress")
            if not em:
                raise RuntimeError("Gmail profile missing emailAddress")
            return str(em)
        except HttpError as e:
            raise RuntimeError(f"Gmail profile failed: {e}") from e
