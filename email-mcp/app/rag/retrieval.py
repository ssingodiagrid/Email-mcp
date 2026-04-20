from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.rag.embeddings import EmbeddingProvider
from app.rag.store import InMemoryVectorStore


@runtime_checkable
class RagRetriever(Protocol):
    def retrieve_exemplars(
        self,
        topic: str | None,
        *,
        k: int = 3,
        instruction: str | None = None,
        intent: str | None = None,
        team: str | None = None,
    ) -> list[str]: ...


class StubRagRetriever:
    """Phase 1-style fallback when corpus is empty or mode is stub."""

    def retrieve_exemplars(
        self,
        topic: str | None,
        *,
        k: int = 3,
        instruction: str | None = None,
        intent: str | None = None,
        team: str | None = None,
    ) -> list[str]:
        _ = (k, instruction, intent, team)
        if not topic:
            return []
        return [
            f"[Exemplar stub] Typical internal note about “{topic}”: "
            "short greeting, one purpose paragraph, clear ask, professional close."
        ]


class VectorRagRetriever:
    """Top-k cosine similarity over in-memory vectors with optional metadata filters."""

    def __init__(
        self,
        store: InMemoryVectorStore,
        embedder: EmbeddingProvider,
        *,
        fallback_to_stub: bool = True,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._fallback = fallback_to_stub
        self._stub = StubRagRetriever()

    def retrieve_exemplars(
        self,
        topic: str | None,
        *,
        k: int = 3,
        instruction: str | None = None,
        intent: str | None = None,
        team: str | None = None,
    ) -> list[str]:
        query_bits = [b for b in (topic, instruction) if b]
        query = " ".join(query_bits).strip()
        if not query:
            if self._fallback:
                return self._stub.retrieve_exemplars(topic, k=k, instruction=instruction, intent=intent, team=team)
            return []

        qvec = self._embedder.embed(query)
        docs = self._store.search(
            qvec,
            k=k,
            topic=topic,
            intent=intent,
            team=team,
        )
        if docs:
            return [d.text for d in docs]
        if self._fallback:
            return self._stub.retrieve_exemplars(topic, k=k, instruction=instruction, intent=intent, team=team)
        return []


def build_rag_retriever(
    *,
    mode: str,
    store: InMemoryVectorStore,
    embedder: EmbeddingProvider,
    fallback_when_empty: bool,
) -> RagRetriever:
    mode = (mode or "vector").strip().lower()
    if mode == "stub":
        return StubRagRetriever()
    return VectorRagRetriever(store, embedder, fallback_to_stub=fallback_when_empty)
