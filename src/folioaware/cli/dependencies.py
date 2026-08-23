"""Dependency composition dedicated to the synchronization command."""

from dataclasses import dataclass

from google import genai
from google.cloud import firestore_v1

from folioaware.adapters.google import (
    FirestoreKnowledgeRepository,
    FirestoreSyncHistoryRepository,
    VertexEmbeddingProvider,
    create_firestore_client,
    create_vertex_client,
)
from folioaware.adapters.local import (
    DeterministicEmbeddingProvider,
    InMemoryKnowledgeRepository,
    InMemorySyncHistoryRepository,
    SystemClock,
    UUID4Provider,
)
from folioaware.application.sync_knowledge import SyncKnowledge
from folioaware.config import SyncSettings
from folioaware.ports.runtime import Clock, IdentifierProvider


@dataclass(frozen=True, slots=True)
class SyncCommandContainer:
    sync_knowledge: SyncKnowledge


def build_sync_container(
    settings: SyncSettings,
    *,
    vertex_client: genai.Client | None = None,
    firestore_client: firestore_v1.Client | None = None,
    clock: Clock | None = None,
    identifiers: IdentifierProvider | None = None,
) -> SyncCommandContainer:
    """Compose only dependencies that can participate in knowledge sync."""
    resolved_clock = clock or SystemClock()
    resolved_identifiers = identifiers or UUID4Provider()
    if settings.backend == "local":
        sync = SyncKnowledge(
            embeddings=DeterministicEmbeddingProvider(),
            repository=InMemoryKnowledgeRepository(),
            history=InMemorySyncHistoryRepository(),
            clock=resolved_clock,
            identifiers=resolved_identifiers,
        )
        return SyncCommandContainer(sync_knowledge=sync)

    if settings.google_cloud_project is None:
        raise ValueError("validated Google sync configuration is incomplete")
    resolved_vertex = vertex_client or create_vertex_client(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        timeout_seconds=settings.google_request_timeout_seconds,
    )
    resolved_firestore = firestore_client or create_firestore_client(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    sync = SyncKnowledge(
        embeddings=VertexEmbeddingProvider(
            client=resolved_vertex,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        ),
        repository=FirestoreKnowledgeRepository(
            client=resolved_firestore,
            timeout_seconds=settings.google_request_timeout_seconds,
        ),
        history=FirestoreSyncHistoryRepository(
            client=resolved_firestore,
            timeout_seconds=settings.google_request_timeout_seconds,
        ),
        clock=resolved_clock,
        identifiers=resolved_identifiers,
    )
    return SyncCommandContainer(sync_knowledge=sync)
