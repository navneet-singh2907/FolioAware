"""Deterministic hashed-token embeddings for local policy verification."""

from __future__ import annotations

import hashlib
import math
import re

from folioaware.domain.knowledge import Embedding, EmbeddingTaskType

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "did",
        "does",
        "expert",
        "has",
        "have",
        "how",
        "ignore",
        "instructions",
        "is",
        "it",
        "know",
        "of",
        "person",
        "previous",
        "claim",
        "they",
        "the",
        "this",
        "to",
        "used",
        "was",
        "were",
        "with",
    }
)


class DeterministicEmbeddingProvider:
    """Small local adapter; not a substitute for a semantic production model."""

    def __init__(self, dimensions: int = 512) -> None:
        if dimensions < 8:
            raise ValueError("local embedding dimensions must be at least 8")
        self._dimensions = dimensions
        self.document_calls = 0
        self.query_calls = 0

    @property
    def model(self) -> str:
        return "local-hash-embedding-v1"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_document(self, text: str) -> Embedding:
        self.document_calls += 1
        return self._embed(text, EmbeddingTaskType.RETRIEVAL_DOCUMENT)

    def embed_query(self, text: str) -> Embedding:
        self.query_calls += 1
        return self._embed(text, EmbeddingTaskType.RETRIEVAL_QUERY)

    def _embed(self, text: str, task_type: EmbeddingTaskType) -> Embedding:
        values = [0.0] * self.dimensions
        tokens = [
            token
            for token in TOKEN_PATTERN.findall(text.casefold())
            if token not in STOP_WORDS
        ]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], byteorder="big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            values[index] += sign

        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude:
            values = [value / magnitude for value in values]
        return Embedding(
            values=tuple(values),
            model=self.model,
            task_type=task_type,
            dimensions=self.dimensions,
        )
