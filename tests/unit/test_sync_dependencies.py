from typing import cast
from unittest.mock import MagicMock

from google import genai
from google.cloud import firestore_v1

from folioaware.cli.dependencies import build_sync_container
from folioaware.config import SyncSettings


def test_google_sync_composition_is_lazy_and_needs_no_runtime_secrets() -> None:
    vertex_client = MagicMock()
    firestore_client = MagicMock()
    settings = SyncSettings(
        backend="google",
        google_cloud_project="synthetic-project",
        embedding_model="embedding-model",
        embedding_dimensions=3,
    )

    container = build_sync_container(
        settings,
        vertex_client=cast(genai.Client, vertex_client),
        firestore_client=cast(firestore_v1.Client, firestore_client),
    )

    assert container.sync_knowledge is not None
    vertex_client.models.embed_content.assert_not_called()
    firestore_client.collection.assert_not_called()
