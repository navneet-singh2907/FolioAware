"""Direct Google SDK adapters for production composition."""

from folioaware.adapters.google.firestore import (
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
    "FirestoreKnowledgeRepository",
    "FirestoreQuestionRepository",
    "VertexEmbeddingProvider",
    "VertexGenerationProvider",
    "create_firestore_client",
    "create_vertex_client",
]
