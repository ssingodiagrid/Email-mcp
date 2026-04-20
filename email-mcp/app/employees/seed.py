from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.employees.repository import EmailExemplarRepository, EmployeeRepository
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.ingest import ingest_records
from app.rag.store import InMemoryVectorStore
from app.storage.models import EmailExemplar, Employee


def seed_demo_if_empty(settings: Settings, session_factory: sessionmaker) -> dict:
    """Insert demo employees + RAG exemplars when tables are empty (no OAuth)."""
    session = session_factory()
    try:
        erepo = EmployeeRepository(session)
        xrepo = EmailExemplarRepository(session)
        if erepo.count_active() > 0:
            session.commit()
            return {"seeded": False, "reason": "employees already present"}

        demo_employees: list[tuple[str, str, str]] = [
            ("Sweeti", "ssweeti@griddynamics.com", "ui"),
            ("Siddharth", "ssingodia@griddynamics.com", "java"),
        ]
        for full_name, email, profile in demo_employees:
            erepo.add(full_name=full_name, email=email, profile=profile)

        exemplars: list[tuple[str, str | None, str, str]] = [
            (
                "scheduling",
                "java",
                "Meeting request — backend sync",
                "Hi,\n\nCould we schedule 30 minutes this week to align on the API contract? "
                "I’m flexible Tue–Thu afternoons.\n\nThanks,\n",
            ),
            (
                "status_update",
                "data_science",
                "Weekly model metrics",
                "Team,\n\nSummary: offline metrics stable; next step is shadow deployment. "
                "Risks: data drift on feature X — monitoring added.\n\nBest,\n",
            ),
            (
                "project_update",
                "ui",
                "Design review follow-up",
                "Hi everyone,\n\nAttached are the updated mocks. Please leave comments by EOD "
                "so we can lock v2 for handoff.\n\nThanks,\n",
            ),
            (
                "follow_up",
                None,
                "Gentle nudge",
                "Hi,\n\nFollowing up on my note from Monday — could you confirm the timeline when you have a moment?\n\nRegards,\n",
            ),
            (
                "onboarding",
                "devops",
                "Access checklist",
                "Welcome aboard,\n\nPlease complete VPN + bastion access first; then open a ticket for prod read-only. "
                "Ping me if anything blocks you.\n\n—",
            ),
            (
                "incident",
                "devops",
                "Incident status",
                "Team,\n\nImpact: partial latency in region A. Mitigation: scaled pool + cache warm. "
                "ETA for all-clear: 45m. Next update at :30.\n\n",
            ),
            (
                "brd_summary",
                "java",
                "BRD excerpt — scope",
                "Stakeholders,\n\nScope for Q2: auth hardening, batch export, and audit log retention. "
                "Out of scope: mobile.\n\n",
            ),
            (
                "retro",
                None,
                "Retro action items",
            "All,\n\nTop 3 actions: (1) tighten deploy checklist, (2) add integration test for payment, "
                "(3) document rollback. Owners in sheet.\n\n",
            ),
        ]
        for fmt, prof, title, body in exemplars:
            xrepo.add(format_kind=fmt, profile=prof, title=title, body_text=body)

        session.commit()
        return {"seeded": True, "employees": len(demo_employees), "exemplars": len(exemplars)}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def merge_exemplars_into_rag_store(
    store: InMemoryVectorStore,
    settings: Settings,
    session_factory: sessionmaker,
) -> int:
    """Embed active `email_exemplars` rows into the vector store (id-stable single-chunk per row)."""
    session = session_factory()
    try:
        rows = session.execute(select(EmailExemplar).where(EmailExemplar.active == True)).scalars().all()  # noqa: E712
        if not rows:
            return 0
        embedder = HashEmbeddingProvider(settings.rag_embedding_dim)
        records: list[dict] = []
        for r in rows:
            team = r.profile or ""
            records.append(
                {
                    "id": r.id,
                    "text": r.body_text,
                    "metadata": {
                        "topic": r.title,
                        "intent": r.format_kind,
                        "team": team,
                        "format_kind": r.format_kind,
                        "profile": team,
                        "source": "email_exemplars",
                    },
                }
            )
        return ingest_records(store, embedder, records, chunk_max_chars=10000, chunk_overlap=0)
    finally:
        session.close()
