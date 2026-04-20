from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.ingest import ingest_jsonl_file
from app.rag.retrieval import RagRetriever, build_rag_retriever
from app.rag.store import InMemoryVectorStore


def create_vector_store(settings: Settings) -> InMemoryVectorStore:
    """Load persisted vectors if present; otherwise ingest JSONL corpus when configured."""
    if settings.rag_store_path:
        p = Path(settings.rag_store_path)
        if p.is_file():
            return InMemoryVectorStore.load_path(p)
    store = InMemoryVectorStore()
    if settings.rag_corpus_path:
        cp = Path(settings.rag_corpus_path)
        if cp.is_file():
            embedder = HashEmbeddingProvider(settings.rag_embedding_dim)
            ingest_jsonl_file(store, embedder, cp)
    return store


def create_rag_retriever(settings: Settings, store: InMemoryVectorStore) -> RagRetriever:
    embedder = HashEmbeddingProvider(settings.rag_embedding_dim)
    return build_rag_retriever(
        mode=settings.rag_mode,
        store=store,
        embedder=embedder,
        fallback_when_empty=settings.rag_fallback_stub,
    )
