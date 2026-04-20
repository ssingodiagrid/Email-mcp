from __future__ import annotations

from email.utils import getaddresses


def parse_address_list(header_value: str) -> list[str]:
    if not header_value:
        return []
    return [a.lower() for _, a in getaddresses([header_value]) if a]


def message_header(msg: dict, name: str) -> str:
    payload = msg.get("payload") or {}
    for h in payload.get("headers") or []:
        if str(h.get("name", "")).lower() == name.lower():
            return str(h.get("value", ""))
    return ""
