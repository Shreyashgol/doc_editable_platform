"""Dependency-free deterministic embedder (default).

Produces a fixed-dimension L2-normalised vector from image bytes (and text) using a hashed
bag-of-pixels / bag-of-tokens projection. It is NOT semantically rich like OpenCLIP, but it is
deterministic, fast, and good enough for exact/near-duplicate detection and for exercising the
full vector-search path with zero ML dependencies. Production swaps in OpenClipEmbedder.
"""

from __future__ import annotations

import hashlib
import math

from ...domain.ports import Embedder


class HashEmbedder(Embedder):
    def __init__(self, dim: int = 512) -> None:
        self._dim = dim

    @property
    def model_name(self) -> str:
        return f"hash-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def _vector_from_bytes(self, data: bytes) -> list[float]:
        vec = [0.0] * self._dim
        # Hash overlapping windows into buckets; stable and order-sensitive.
        digest = hashlib.sha256(data).digest()
        # Seed with the content digest, then fold the byte stream into buckets.
        for i, byte in enumerate(data[:4096]):
            bucket = (byte * 31 + i) % self._dim
            vec[bucket] += 1.0
        for i, b in enumerate(digest):
            vec[(b + i) % self._dim] += 2.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_image(self, crop_png: bytes) -> list[float]:
        return self._vector_from_bytes(crop_png)

    def embed_text(self, text: str) -> list[float]:
        return self._vector_from_bytes(text.encode("utf-8"))
