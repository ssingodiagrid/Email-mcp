from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...

    @property
    def dimensions(self) -> int: ...


class HashEmbeddingProvider:
    """Deterministic pseudo-embeddings (no external API). Suitable for CI and offline demos."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be >= 8")
        self._dim = dimensions

    @property
    def dimensions(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        out: list[float] = []
        block = seed
        while len(out) < self._dim:
            block = hashlib.sha256(block).digest()
            for b in block:
                out.append((b / 255.0) * 2.0 - 1.0)
        vec = out[: self._dim]
        # L2-normalize for cosine similarity
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
