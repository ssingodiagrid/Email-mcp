from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.config import Settings, get_settings
from app.employees.directory import DatabaseDirectoryAdapter
from app.employees.registry import EmployeeRegistry
from app.employees.repository import EmailExemplarRepository, EmployeeRepository
from app.employees.seed import merge_exemplars_into_rag_store, seed_demo_if_empty
from app.gmail.client import GmailClient
from app.gmail.factory import build_gmail_client
from app.gmail.stub import StubGmailClient
from app.policy.directory import DirectoryAdapter, StubDirectoryAdapter
from app.policy.recipient_policy import RecipientPolicy
from app.replies.tracker import ReplyTracker
from app.rag.factory import create_rag_retriever, create_vector_store
from app.rag.ingest import ingest_jsonl_file, ingest_records
from app.rag.retrieval import RagRetriever
from app.rag.store import InMemoryVectorStore
from app.storage.db import get_session_factory, init_db
from app.storage.models import DraftStatus
from app.storage.repository import DraftRepository
from app.workflows.graph import build_send_workflow


@dataclass
class StartResult:
    thread_id: str
    error: str | None = None
    pending: dict | None = None


@dataclass
class ResumeResult:
    thread_id: str
    cancelled: bool = False
    provider_message_id: str | None = None
    error: str | None = None
    track_id: str | None = None


class SendWorkflowOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        policy: RecipientPolicy,
        directory: DirectoryAdapter,
        rag: RagRetriever,
        rag_store: InMemoryVectorStore,
        gmail: GmailClient,
        checkpointer: SqliteSaver,
        reply_tracker: ReplyTracker,
        employee_registry: EmployeeRegistry,
    ) -> None:
        self._settings = settings
        self._policy = policy
        self._directory = directory
        self._rag = rag
        self._rag_store = rag_store
        self._gmail = gmail
        self._checkpointer = checkpointer
        self._reply_tracker = reply_tracker
        self._employee_registry = employee_registry
        self._app = build_send_workflow(
            policy,
            rag,
            gmail,
            checkpointer,
            rag_top_k=settings.rag_top_k,
            employee_registry=employee_registry,
        )
        self._sessions = get_session_factory(settings)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> SendWorkflowOrchestrator:
        settings = settings or get_settings()
        init_db(settings)
        sessions = get_session_factory(settings)
        if settings.seed_demo_data:
            seed_demo_if_empty(settings, sessions)
        os.makedirs(os.path.dirname(settings.langgraph_checkpoint_path) or ".", exist_ok=True)
        conn = sqlite3.connect(settings.langgraph_checkpoint_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        checkpointer.setup()
        policy = RecipientPolicy(
            settings.domain_list(),
            allow_subdomains=settings.allow_subdomains,
        )
        try:
            gmail: GmailClient = build_gmail_client(settings)
        except ValueError as e:
            raise ValueError(
                f"{e} (or set EMAIL_MCP_USE_STUB_GMAIL=true for stub mode)"
            ) from e
        rag_store = create_vector_store(settings)
        if settings.rag_hydrate_from_db_exemplars:
            merge_exemplars_into_rag_store(rag_store, settings, sessions)
        rag = create_rag_retriever(settings, rag_store)
        reply_tracker = ReplyTracker(settings=settings, gmail=gmail, session_factory=sessions)
        employee_registry = EmployeeRegistry(
            session_factory=sessions,
            enabled=settings.require_employee_registry,
        )
        if settings.require_employee_registry:
            directory: DirectoryAdapter = DatabaseDirectoryAdapter(sessions, policy)
        else:
            directory = StubDirectoryAdapter()
        return cls(
            settings=settings,
            policy=policy,
            directory=directory,
            rag=rag,
            rag_store=rag_store,
            gmail=gmail,
            checkpointer=checkpointer,
            reply_tracker=reply_tracker,
            employee_registry=employee_registry,
        )

    def resolve_recipients(self, names: list[str]) -> dict:
        matches: list[dict] = []
        violations: list[dict] = []
        for name in names:
            found = self._directory.lookup_by_name(name)
            if not found:
                matches.append({"query": name, "candidates": []})
                continue
            ok: list[dict] = []
            for m in found:
                try:
                    self._policy.ensure_allowed([m.email], [], [])
                    ok.append(
                        {
                            "display_name": m.display_name,
                            "email": m.email,
                            "profile": m.profile,
                        }
                    )
                except PermissionError:
                    violations.append({"query": name, "email": m.email, "reason": "domain_not_allowlisted"})
            matches.append({"query": name, "candidates": ok})
        return {"matches": matches, "violations": violations}

    def read_gmail_thread(self, gmail_thread_id: str) -> dict:
        """Load a Gmail conversation by provider thread id (not the LangGraph workflow thread id)."""
        return self._gmail.get_thread(gmail_thread_id)

    def rag_status(self) -> dict:
        return {
            "mode": self._settings.rag_mode,
            "chunks": len(self._rag_store),
            "top_k": self._settings.rag_top_k,
            "embedding_dim": self._settings.rag_embedding_dim,
            "persist_path": self._settings.rag_store_path,
            "fallback_stub": self._settings.rag_fallback_stub,
        }

    def rag_ingest_documents(self, documents: list[dict]) -> dict:
        from app.rag.embeddings import HashEmbeddingProvider

        embedder = HashEmbeddingProvider(self._settings.rag_embedding_dim)
        added = ingest_records(self._rag_store, embedder, documents)
        if self._settings.rag_store_path:
            self._rag_store.save_path(self._settings.rag_store_path)
        return {"ingested_chunks": added, "total_chunks": len(self._rag_store)}

    def rag_search(
        self,
        query: str,
        k: int = 5,
        topic: str | None = None,
        intent: str | None = None,
        team: str | None = None,
    ) -> dict:
        from app.rag.embeddings import HashEmbeddingProvider

        embedder = HashEmbeddingProvider(self._settings.rag_embedding_dim)
        qvec = embedder.embed(query)
        docs = self._rag_store.search(qvec, k=k, topic=topic, intent=intent, team=team)
        return {
            "results": [{"id": d.id, "text": d.text, "metadata": d.metadata} for d in docs],
        }

    def track_reply_status(self, track_id: str) -> dict:
        """Refresh reply state from Gmail for a tracked send (poll from gateway/scheduler)."""
        return self._reply_tracker.track_reply_status(track_id)

    def detect_no_response(self, track_id: str) -> dict:
        """Run `track_reply_status` then mark `no_response` if SLA passed and still awaiting reply."""
        return self._reply_tracker.detect_no_response(track_id)

    def list_tracked_sends(self, limit: int = 50) -> dict:
        return self._reply_tracker.list_tracked_sends(limit=limit)

    def stub_inject_gmail_reply(self, gmail_thread_id: str, from_email: str) -> dict:
        """Test/dev: simulate an inbound reply in the stub Gmail client."""
        if not isinstance(self._gmail, StubGmailClient):
            return {"error": "only available when EMAIL_MCP_USE_STUB_GMAIL=true"}
        mid = self._gmail.add_inbound_reply(gmail_thread_id, from_email)
        return {"injected_message_id": mid, "gmail_thread_id": gmail_thread_id}

    def employee_list(self, limit: int = 200) -> dict:
        session = self._sessions()
        try:
            repo = EmployeeRepository(session)
            rows = repo.list_active(limit=limit)
            return {
                "employees": [
                    {"id": e.id, "full_name": e.full_name, "email": e.email, "profile": e.profile}
                    for e in rows
                ]
            }
        finally:
            session.close()

    def employee_add(self, full_name: str, email: str, profile: str) -> dict:
        from sqlalchemy.exc import IntegrityError

        session = self._sessions()
        try:
            repo = EmployeeRepository(session)
            repo.add(full_name=full_name, email=email, profile=profile)
            session.commit()
            return {"ok": True, "email": email.strip().lower()}
        except IntegrityError as e:
            session.rollback()
            return {"ok": False, "error": f"duplicate or invalid email: {e}"}
        finally:
            session.close()

    def employee_deactivate(self, email: str) -> dict:
        session = self._sessions()
        try:
            repo = EmployeeRepository(session)
            ok = repo.deactivate_by_email(email)
            session.commit()
            return {"ok": ok}
        finally:
            session.close()

    def exemplar_list(self) -> dict:
        session = self._sessions()
        try:
            repo = EmailExemplarRepository(session)
            rows = repo.list_active()
            return {
                "exemplars": [
                    {
                        "id": x.id,
                        "format_kind": x.format_kind,
                        "profile": x.profile,
                        "title": x.title,
                        "preview": x.body_text[:120],
                    }
                    for x in rows
                ]
            }
        finally:
            session.close()

    def exemplar_add(
        self,
        format_kind: str,
        title: str,
        body_text: str,
        profile: str | None = None,
    ) -> dict:
        session = self._sessions()
        try:
            repo = EmailExemplarRepository(session)
            row = repo.add(format_kind=format_kind, title=title, body_text=body_text, profile=profile)
            session.commit()
            return {"ok": True, "id": row.id}
        finally:
            session.close()

    def reload_rag_from_exemplar_tables(self) -> dict:
        self._rag_store.clear()
        if self._settings.rag_corpus_path and Path(self._settings.rag_corpus_path).is_file():
            from app.rag.embeddings import HashEmbeddingProvider

            ingest_jsonl_file(
                self._rag_store,
                HashEmbeddingProvider(self._settings.rag_embedding_dim),
                self._settings.rag_corpus_path,
            )
        n = merge_exemplars_into_rag_store(self._rag_store, self._settings, self._sessions)
        if self._settings.rag_store_path:
            self._rag_store.save_path(self._settings.rag_store_path)
        return {"db_exemplar_chunks": n, "total_chunks": len(self._rag_store)}

    def start_send(
        self,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        topic: str | None = None,
        instruction: str | None = None,
    ) -> StartResult:
        thread_id = str(uuid.uuid4())
        cc = cc or []
        bcc = bcc or []
        config = {"configurable": {"thread_id": thread_id}}
        initial = {
            "thread_id": thread_id,
            "to": list(to),
            "cc": list(cc),
            "bcc": list(bcc),
            "topic": topic,
            "instruction": instruction,
        }
        out = self._app.invoke(initial, config)
        session = self._sessions()
        try:
            repo = DraftRepository(session)
            if out.get("error"):
                d = repo.create_draft(
                    thread_id=thread_id,
                    subject="(validation failed)",
                    body=out["error"],
                    to_addresses=list(to),
                    cc_addresses=list(cc),
                    bcc_addresses=list(bcc),
                    version_source="system",
                )
                repo.set_status(d, DraftStatus.FAILED_VALIDATION)
                session.commit()
                return StartResult(thread_id=thread_id, error=out["error"])

            interrupts = out.get("__interrupt__") or []
            if not interrupts:
                session.commit()
                return StartResult(thread_id=thread_id, error="workflow did not reach approval gate")

            intr = interrupts[0]
            pending = getattr(intr, "value", intr)
            snap = self._app.get_state(config)
            vals = snap.values
            d = repo.create_draft(
                thread_id=thread_id,
                subject=vals.get("subject", ""),
                body=vals.get("body", ""),
                to_addresses=list(vals.get("to", [])),
                cc_addresses=list(vals.get("cc", []) or []),
                bcc_addresses=list(vals.get("bcc", []) or []),
                version_source="model",
            )
            repo.set_status(d, DraftStatus.PENDING_APPROVAL)
            session.commit()
            return StartResult(thread_id=thread_id, pending=pending if isinstance(pending, dict) else {"value": pending})
        finally:
            session.close()

    def submit_approval(
        self,
        *,
        thread_id: str,
        action: str,
        approver_id: str,
        subject: str | None = None,
        body: str | None = None,
        to: list[str] | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> ResumeResult:
        config = {"configurable": {"thread_id": thread_id}}
        session = self._sessions()
        try:
            repo = DraftRepository(session)
            draft = repo.get_by_thread_id(thread_id)
            if draft is None:
                return ResumeResult(thread_id=thread_id, error="unknown thread_id")
            if draft.status != DraftStatus.PENDING_APPROVAL.value:
                return ResumeResult(thread_id=thread_id, error=f"draft not pending approval (status={draft.status})")

            snap = self._app.get_state(config)
            vals = dict(snap.values)
            sub = subject if subject is not None else vals.get("subject", "")
            bod = body if body is not None else vals.get("body", "")
            to_f = list(to if to is not None else vals.get("to", []))
            cc_f = list(cc if cc is not None else vals.get("cc", []) or [])
            bcc_f = list(bcc if bcc is not None else vals.get("bcc", []) or [])

            if action == "cancel":
                self._app.invoke(Command(resume={"action": "cancel"}), config)
                repo.set_status(draft, DraftStatus.CANCELLED)
                session.commit()
                return ResumeResult(thread_id=thread_id, cancelled=True)

            if action != "approve":
                return ResumeResult(thread_id=thread_id, error="action must be approve or cancel")

            try:
                self._policy.ensure_allowed(to_f, cc_f, bcc_f)
                self._employee_registry.ensure_recipients_registered(to_f, cc_f, bcc_f)
            except PermissionError as e:
                return ResumeResult(thread_id=thread_id, error=str(e))

            repo.add_human_version(
                draft,
                subject=sub,
                body=bod,
                to_addresses=to_f,
                cc_addresses=cc_f,
                bcc_addresses=bcc_f,
            )
            repo.record_approval(
                draft,
                approver_id=approver_id,
                subject=sub,
                body=bod,
                to_addresses=to_f,
                cc_addresses=cc_f,
                bcc_addresses=bcc_f,
            )
            session.commit()

            self._app.invoke(
                Command(
                    resume={
                        "action": "approve",
                        "subject": sub,
                        "body": bod,
                        "to": to_f,
                        "cc": cc_f,
                        "bcc": bcc_f,
                    }
                ),
                config,
            )

            final = self._app.get_state(config).values
            session2 = self._sessions()
            try:
                repo2 = DraftRepository(session2)
                d2 = repo2.get_by_thread_id(thread_id)
                if d2 is None:
                    return ResumeResult(thread_id=thread_id, error="draft missing after send")
                if final.get("cancelled"):
                    repo2.set_status(d2, DraftStatus.CANCELLED)
                    session2.commit()
                    return ResumeResult(thread_id=thread_id, cancelled=True)
                mid = final.get("provider_message_id")
                if not mid:
                    session2.commit()
                    return ResumeResult(thread_id=thread_id, error="send did not produce provider_message_id")
                repo2.record_send(d2, provider_message_id=str(mid))
                repo2.set_status(d2, DraftStatus.SENT)
                session2.commit()
                meta: dict | None = None
                try:
                    meta = self._gmail.get_message(str(mid))
                except Exception:  # noqa: BLE001
                    meta = None
                gtid = (meta or {}).get("threadId")
                track_id = self._reply_tracker.register_after_send(
                    draft_id=d2.id,
                    workflow_thread_id=thread_id,
                    gmail_message_id=str(mid),
                    gmail_thread_id=str(gtid) if gtid else None,
                    to_addresses=to_f,
                    cc_addresses=cc_f,
                )
                return ResumeResult(
                    thread_id=thread_id,
                    provider_message_id=str(mid),
                    track_id=track_id,
                )
            finally:
                session2.close()
        finally:
            session.close()

    def get_workflow_status(self, thread_id: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        session = self._sessions()
        try:
            repo = DraftRepository(session)
            draft = repo.get_by_thread_id(thread_id)
            db_snapshot = None
            if draft:
                db_snapshot = {
                    "draft_id": draft.id,
                    "status": draft.status,
                    "created_at": draft.created_at.isoformat(),
                    "updated_at": draft.updated_at.isoformat(),
                }
            try:
                snap = self._app.get_state(config)
                graph_snapshot = {
                    "next": list(snap.next),
                    "values": dict(snap.values),
                }
            except Exception:
                graph_snapshot = None
            return {"thread_id": thread_id, "database": db_snapshot, "graph": graph_snapshot}
        finally:
            session.close()
