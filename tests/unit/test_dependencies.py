from typing import cast
from unittest.mock import MagicMock

from google import genai
from google.cloud import firestore_v1

from folioaware.adapters.google import (
    FirestoreInsightRepository,
    FirestoreKnowledgeRepository,
    FirestoreQuestionRepository,
    VertexEmbeddingProvider,
    VertexGenerationProvider,
)
from folioaware.api.dependencies import (
    GoogleApplicationContainer,
    LocalApplicationContainer,
    build_container,
    build_google_container,
)
from folioaware.config import Settings


def test_default_composition_stays_offline_and_local() -> None:
    container = build_container(Settings())

    assert isinstance(container, LocalApplicationContainer)


def test_google_composition_accepts_injected_clients_without_api_calls() -> None:
    vertex_client = MagicMock()
    firestore_client = MagicMock()
    settings = Settings(
        backend="google",
        google_cloud_project="synthetic-project",
        generation_model="generation-model",
    )

    container = build_google_container(
        settings,
        vertex_client=cast(genai.Client, vertex_client),
        firestore_client=cast(firestore_v1.Client, firestore_client),
    )

    assert isinstance(container, GoogleApplicationContainer)
    assert isinstance(container.embeddings, VertexEmbeddingProvider)
    assert isinstance(container.generation, VertexGenerationProvider)
    assert isinstance(container.knowledge, FirestoreKnowledgeRepository)
    assert isinstance(container.questions, FirestoreQuestionRepository)
    assert isinstance(container.insights, FirestoreInsightRepository)
    vertex_client.models.embed_content.assert_not_called()
    vertex_client.models.generate_content.assert_not_called()
    firestore_client.collection.assert_not_called()
