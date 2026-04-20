from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DirectoryMatch:
    display_name: str
    email: str
    profile: str | None = None


@runtime_checkable
class DirectoryAdapter(Protocol):
    def lookup_by_name(self, name: str) -> list[DirectoryMatch]: ...


class StubDirectoryAdapter:
    """Development directory: keyed by lowercased name fragments."""

    def __init__(self, people: dict[str, list[DirectoryMatch]] | None = None) -> None:
        self._people = {k.lower(): v for k, v in (people or _DEFAULT_STUB).items()}

    def lookup_by_name(self, name: str) -> list[DirectoryMatch]:
        key = name.strip().lower()
        if key in self._people:
            return list(self._people[key])
        matches: list[DirectoryMatch] = []
        for bucket in self._people.values():
            for m in bucket:
                if key in m.display_name.lower() or key in m.email.lower():
                    matches.append(m)
        # de-dupe by email
        seen: set[str] = set()
        out: list[DirectoryMatch] = []
        for m in matches:
            if m.email not in seen:
                seen.add(m.email)
                out.append(m)
        return out


_DEFAULT_STUB: dict[str, list[DirectoryMatch]] = {
    "sweeti": [DirectoryMatch("Sweeti", "sweeti@griddynamics.com", "ui")],
    "siddharth": [DirectoryMatch("Siddharth", "siddharth@griddynamics.com", "java")],
}
