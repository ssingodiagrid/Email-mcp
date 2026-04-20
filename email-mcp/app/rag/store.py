from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class RagDocument:
    id: str
    text: str
    metadata: dict[str, Any]
    embedding: list[float]


def metadata_matches(meta: dict[str, Any], *, topic: str | None, intent: str | None, team: str | None) -> bool:
    if topic:
        mt = str(meta.get("topic", "")).lower()
        tt = topic.lower()
        if tt not in mt and mt not in tt and mt != tt:
            return False
    if intent:
        if str(meta.get("intent", "")).lower() != intent.lower():
            return False
    if team:
        ms = str(meta.get("team", "")).lower()
        if team.lower() not in ms:
            return False
    return True


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._docs: dict[str, RagDocument] = {}

    def __len__(self) -> int:
        return len(self._docs)

    def clear(self) -> None:
        self._docs.clear()

    def add(self, doc: RagDocument) -> None:
        self._docs[doc.id] = doc

    def add_text(
        self,
        *,
        text: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> str:
        rid = doc_id or str(uuid.uuid4())
        self.add(RagDocument(id=rid, text=text, metadata=dict(metadata or {}), embedding=embedding))
        return rid

    def search(
        self,
        query_embedding: list[float],
        *,
        k: int,
        topic: str | None = None,
        intent: str | None = None,
        team: str | None = None,
    ) -> list[RagDocument]:
        scored: list[tuple[float, RagDocument]] = []
        for doc in self._docs.values():
            if not metadata_matches(doc.metadata, topic=topic, intent=intent, team=team):
                continue
            scored.append((_cosine(query_embedding, doc.embedding), doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:k]]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "documents": [
                {"id": d.id, "text": d.text, "metadata": d.metadata, "embedding": d.embedding}
                for d in self._docs.values()
            ]
        }

    @classmethod
    def from_jsonable(cls, payload: dict[str, Any]) -> InMemoryVectorStore:
        store = cls()
        for row in payload.get("documents", []):
            store.add(
                RagDocument(
                    id=str(row["id"]),
                    text=str(row["text"]),
                    metadata=dict(row.get("metadata") or {}),
                    embedding=[float(x) for x in row["embedding"]],
                )
            )
        return store

    def save_path(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_jsonable(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load_path(cls, path: str | Path) -> InMemoryVectorStore:
        p = Path(path)
        if not p.is_file():
            return cls()
        payload = json.loads(p.read_text(encoding="utf-8"))
        return cls.from_jsonable(payload)
