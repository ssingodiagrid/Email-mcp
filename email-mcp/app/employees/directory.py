from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.policy.directory import DirectoryMatch
from app.policy.recipient_policy import RecipientPolicy
from app.employees.repository import EmployeeRepository


class DatabaseDirectoryAdapter:
    """Resolve names or emails against the `employees` table only."""

    def __init__(
        self,
        session_factory: sessionmaker,
        policy: RecipientPolicy,
    ) -> None:
        self._session_factory = session_factory
        self._policy = policy

    def lookup_by_name(self, name: str) -> list[DirectoryMatch]:
        session = self._session_factory()
        try:
            repo = EmployeeRepository(session)
            found = repo.search(name)
            out: list[DirectoryMatch] = []
            for e in found:
                try:
                    self._policy.ensure_allowed([e.email], [], [])
                except PermissionError:
                    continue
                out.append(DirectoryMatch(display_name=e.full_name, email=e.email, profile=e.profile))
            seen: set[str] = set()
            deduped: list[DirectoryMatch] = []
            for m in out:
                if m.email not in seen:
                    seen.add(m.email)
                    deduped.append(m)
            return deduped
        finally:
            session.close()
