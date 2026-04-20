"""
Ingestion contract (Phase 3)

- **Source of truth**: exports from approved internal mail corpus, templates, or JSONL you generate offline.
- **Chunking**: `chunk_text` splits long bodies on paragraph boundaries; tune `max_chars` / `overlap`.
- **Metadata**: `topic`, `intent`, `team`, `source`, `redacted` (bool) — filters at query time.
- **Redaction**: run *before* calling ingest in your pipeline; this module does not auto-redact PII.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from app.rag.embeddings import EmbeddingProvider
from app.rag.store import InMemoryVectorStore


def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 120) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end]
        if end < len(text):
            cut = chunk.rfind("\n\n")
            if cut > max_chars // 3:
                chunk = chunk[:cut]
                end = start + cut
        parts.append(chunk.strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return [p for p in parts if p]


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    p = Path(path)
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def ingest_records(
    store: InMemoryVectorStore,
    embedder: EmbeddingProvider,
    records: list[dict[str, Any]],
    *,
    chunk_max_chars: int = 1200,
    chunk_overlap: int = 120,
) -> int:
    """Insert records into the store. Each record: text (str), optional metadata dict, optional id."""
    added = 0
    for rec in records:
        text = str(rec.get("text", "")).strip()
        if not text:
            continue
        base_meta = dict(rec.get("metadata") or {})
        for key in ("topic", "intent", "team", "source", "redacted"):
            if key in rec and rec[key] is not None and key not in base_meta:
                base_meta[key] = rec[key]
        chunks = chunk_text(text, max_chars=chunk_max_chars, overlap=chunk_overlap)
        for i, ch in enumerate(chunks):
            meta = {**base_meta, "chunk_index": i, "chunk_total": len(chunks)}
            emb = embedder.embed(ch)
            doc_id = None
            if rec.get("id") and len(chunks) == 1:
                doc_id = str(rec["id"])
            elif rec.get("id"):
                doc_id = f"{rec['id']}#{i}"
            store.add_text(text=ch, embedding=emb, metadata=meta, doc_id=doc_id)
            added += 1
    return added


def ingest_jsonl_file(
    store: InMemoryVectorStore,
    embedder: EmbeddingProvider,
    path: str | Path,
    **kwargs: Any,
) -> int:
    return ingest_records(store, embedder, list(iter_jsonl(path)), **kwargs)
