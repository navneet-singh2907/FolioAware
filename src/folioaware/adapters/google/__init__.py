"""Direct Google SDK adapters for production composition."""

from folioaware.adapters.google.firestore import (
    FirestoreInsightRepository,
    FirestoreKnowledgeRepository,
    FirestoreQuestionRepository,
    create_firestore_client,
)
from folioaware.adapters.google.vertex import (
    VertexEmbeddingProvider,
    VertexGenerationProvider,
    create_vertex_client,
)

__all__ = [
    "FirestoreInsightRepository",
    "FirestoreKnowledgeRepository",
    "FirestoreQuestionRepository",
    "VertexEmbeddingProvider",
    "VertexGenerationProvider",
    "create_firestore_client",
    "create_vertex_client",
]
