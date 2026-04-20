from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.employees.repository import EmployeeRepository


class EmployeeRegistry:
    """Enforce that all To/Cc/Bcc addresses exist in `employees` (for review-time adds too)."""

    def __init__(self, *, session_factory: sessionmaker, enabled: bool = True) -> None:
        self._session_factory = session_factory
        self._enabled = enabled

    def ensure_recipients_registered(self, to: list[str], cc: list[str] | None = None, bcc: list[str] | None = None) -> None:
        if not self._enabled:
            return
        cc = cc or []
        bcc = bcc or []
        combined = [x.strip() for x in (to + cc + bcc) if x and str(x).strip()]
        if not combined:
            raise PermissionError("At least one recipient is required")
        session = self._session_factory()
        try:
            repo = EmployeeRepository(session)
            for addr in combined:
                if not repo.is_active_email(addr):
                    raise PermissionError(
                        f"Recipient not in employee directory: {addr}. "
                        "Add them with the employee_add tool or ask an admin."
                    )
        finally:
            session.close()
