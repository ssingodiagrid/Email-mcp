from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class DraftStatus(str, enum.Enum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED_VALIDATION = "failed_validation"


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default=DraftStatus.PROPOSED.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    versions: Mapped[list[DraftVersion]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    approvals: Mapped[list[ApprovalRecord]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    sends: Mapped[list[SendRecord]] = relationship(back_populates="draft", cascade="all, delete-orphan")


class DraftVersion(Base):
    __tablename__ = "draft_versions"
    __table_args__ = (UniqueConstraint("draft_id", "version_no", name="uq_draft_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(String(36), ForeignKey("drafts.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column()
    source: Mapped[str] = mapped_column(String(32))  # model | human
    subject: Mapped[str] = mapped_column(String(998))
    body: Mapped[str] = mapped_column(Text())
    to_addresses: Mapped[list[str]] = mapped_column(JSON)
    cc_addresses: Mapped[list[str]] = mapped_column(JSON)
    bcc_addresses: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    draft: Mapped[Draft] = relationship(back_populates="versions")


class ApprovalRecord(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(String(36), ForeignKey("drafts.id", ondelete="CASCADE"))
    approver_id: Mapped[str] = mapped_column(String(256))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload_fingerprint: Mapped[str] = mapped_column(String(128))

    draft: Mapped[Draft] = relationship(back_populates="approvals")


class SendRecord(Base):
    __tablename__ = "sends"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(String(36), ForeignKey("drafts.id", ondelete="CASCADE"))
    provider_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    draft: Mapped[Draft] = relationship(back_populates="sends")


class Employee(Base):
    """Org directory: only these people are valid recipients when registry enforcement is on."""

    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name: Mapped[str] = mapped_column(String(256))
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    profile: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailExemplar(Base):
    """Seed / admin-managed email templates for RAG (format + optional profile)."""

    __tablename__ = "email_exemplars"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    format_kind: Mapped[str] = mapped_column(String(64), index=True)
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    body_text: Mapped[str] = mapped_column(Text())
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrackedSend(Base):
    """Phase 4 — SLA / reply tracking for outbound sends."""

    __tablename__ = "tracked_sends"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True)
    workflow_thread_id: Mapped[str] = mapped_column(String(64), index=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(256))
    to_addresses: Mapped[list[str]] = mapped_column(JSON)
    cc_addresses: Mapped[list[str]] = mapped_column(JSON)
    mailbox_address: Mapped[str] = mapped_column(String(256))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sla_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="awaiting_reply", index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_gmail_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reply_from: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
