from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.storage.models import EmailExemplar, Employee


class EmployeeRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def count_active(self) -> int:
        return int(
            self._s.execute(select(func.count()).select_from(Employee).where(Employee.active == True)).scalar()  # noqa: E712
            or 0
        )

    def is_active_email(self, email: str) -> bool:
        e = email.strip().lower()
        row = self._s.execute(
            select(Employee).where(Employee.active == True, func.lower(Employee.email) == e)  # noqa: E712
        ).scalar_one_or_none()
        return row is not None

    def search(self, query: str) -> list[Employee]:
        q = query.strip()
        if not q:
            return []
        ql = q.lower()
        if "@" in q:
            stmt = select(Employee).where(Employee.active == True, func.lower(Employee.email) == ql)  # noqa: E712
        else:
            stmt = select(Employee).where(
                Employee.active == True,  # noqa: E712
                or_(
                    Employee.full_name.ilike(f"%{q}%"),
                    func.lower(Employee.email).like(f"%{ql}%"),
                ),
            )
        return list(self._s.execute(stmt).scalars().all())

    def list_active(self, *, limit: int = 500) -> list[Employee]:
        stmt = select(Employee).where(Employee.active == True).order_by(Employee.full_name).limit(limit)  # noqa: E712
        return list(self._s.execute(stmt).scalars().all())

    def add(
        self,
        *,
        full_name: str,
        email: str,
        profile: str,
        active: bool = True,
    ) -> Employee:
        row = Employee(
            full_name=full_name.strip(),
            email=email.strip().lower(),
            profile=profile.strip().lower().replace(" ", "_"),
            active=active,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def deactivate_by_email(self, email: str) -> bool:
        row = self._s.execute(
            select(Employee).where(func.lower(Employee.email) == email.strip().lower())
        ).scalar_one_or_none()
        if row is None:
            return False
        row.active = False
        self._s.flush()
        return True


class EmailExemplarRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def count_active(self) -> int:
        return int(
            self._s.execute(
                select(func.count()).select_from(EmailExemplar).where(EmailExemplar.active == True)  # noqa: E712
            ).scalar()
            or 0
        )

    def list_active(self) -> list[EmailExemplar]:
        stmt = select(EmailExemplar).where(EmailExemplar.active == True).order_by(EmailExemplar.format_kind)  # noqa: E712
        return list(self._s.execute(stmt).scalars().all())

    def add(
        self,
        *,
        format_kind: str,
        title: str,
        body_text: str,
        profile: str | None = None,
        active: bool = True,
    ) -> EmailExemplar:
        row = EmailExemplar(
            format_kind=format_kind.strip().lower().replace(" ", "_"),
            title=title.strip(),
            body_text=body_text.strip(),
            profile=(profile.strip().lower().replace(" ", "_") if profile else None),
            active=active,
        )
        self._s.add(row)
        self._s.flush()
        return row
