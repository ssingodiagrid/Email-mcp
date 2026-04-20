from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GmailClient(Protocol):
    def send_message(
        self,
        *,
        subject: str,
        body: str,
        to: list[str],
        cc: list[str],
        bcc: list[str],
    ) -> str: ...

    def get_thread(self, thread_id: str) -> dict: ...

    def get_message(self, message_id: str) -> dict: ...

    def resolve_mailbox_address(self) -> str: ...
