"""Deterministic local adapters for development and tests."""

from folioaware.adapters.local.embeddings import DeterministicEmbeddingProvider
from folioaware.adapters.local.generation import DeterministicGenerationProvider
from folioaware.adapters.local.repositories import (
    InMemoryKnowledgeRepository,
    InMemoryQuestionRepository,
)
from folioaware.adapters.local.runtime import SystemClock, UUID4Provider

__all__ = [
    "DeterministicEmbeddingProvider",
    "DeterministicGenerationProvider",
    "InMemoryKnowledgeRepository",
    "InMemoryQuestionRepository",
    "SystemClock",
    "UUID4Provider",
]
