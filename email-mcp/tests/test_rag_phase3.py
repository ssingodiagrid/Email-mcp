from __future__ import annotations

from app.config import Settings
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.ingest import ingest_records
from app.rag.retrieval import VectorRagRetriever
from app.rag.store import InMemoryVectorStore
from app.workflows.orchestrator import SendWorkflowOrchestrator


def test_vector_store_search_orders_by_similarity():
    store = InMemoryVectorStore()
    emb = HashEmbeddingProvider(64)
    q = emb.embed("rollout schedule")
    store.add_text(text="alpha", embedding=emb.embed("unrelated pizza"), metadata={"topic": "rollout"})
    store.add_text(text="beta", embedding=q, metadata={"topic": "rollout"})
    hits = store.search(q, k=2, topic="rollout")
    assert [h.text for h in hits] == ["beta", "alpha"]


def test_retriever_respects_topic_filter():
    store = InMemoryVectorStore()
    emb = HashEmbeddingProvider(64)
    ingest_records(
        store,
        emb,
        [
            {"text": "HR onboarding checklist", "topic": "hr"},
            {"text": "Engineering deploy steps", "topic": "eng"},
        ],
    )
    r = VectorRagRetriever(store, emb, fallback_to_stub=False)
    out = r.retrieve_exemplars("engineering", k=3, instruction="deploy steps")
    assert any("deploy" in s.lower() for s in out)
    assert not any("onboarding" in s.lower() for s in out)


def test_draft_includes_ingested_exemplar_when_no_fallback(tmp_path):
    db = tmp_path / "a.db"
    cp = tmp_path / "c.sqlite"
    settings = Settings(
        database_url=f"sqlite:///{db}",
        langgraph_checkpoint_path=str(cp),
        rag_mode="vector",
        rag_fallback_stub=False,
        rag_top_k=2,
        rag_embedding_dim=128,
    )
    orch = SendWorkflowOrchestrator.from_settings(settings)
    orch.rag_ingest_documents(
        [
            {
                "text": "Use a short greeting, one paragraph for context, and a numbered ask for rollout status.",
                "topic": "rollout",
            }
        ]
    )
    start = orch.start_send(
        to=["siddharth@griddynamics.com"],
        topic="rollout",
        instruction="Weekly status",
    )
    assert start.pending
    body = start.pending.get("body", "")
    assert "numbered ask" in body
