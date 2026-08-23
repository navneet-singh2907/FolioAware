"""Deterministic local adapters for development and tests."""

from folioaware.adapters.local.embeddings import DeterministicEmbeddingProvider
from folioaware.adapters.local.generation import DeterministicGenerationProvider
from folioaware.adapters.local.repositories import (
    InMemoryInsightRepository,
    InMemoryKnowledgeRepository,
    InMemoryQuestionRepository,
    InMemorySyncHistoryRepository,
)
from folioaware.adapters.local.runtime import SystemClock, UUID4Provider

__all__ = [
    "DeterministicEmbeddingProvider",
    "DeterministicGenerationProvider",
    "InMemoryInsightRepository",
    "InMemoryKnowledgeRepository",
    "InMemoryQuestionRepository",
    "InMemorySyncHistoryRepository",
    "SystemClock",
    "UUID4Provider",
]
