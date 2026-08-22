"""Embedding provider capability."""

from typing import Protocol

from folioaware.domain.knowledge import Embedding


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_document(self, text: str) -> Embedding: ...

    def embed_query(self, text: str) -> Embedding: ...
