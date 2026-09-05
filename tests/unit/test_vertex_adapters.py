from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import google.auth
import pytest
from google import genai
from google.auth.credentials import Credentials
from google.genai import types
from google.genai.errors import APIError

from folioaware.adapters.google.vertex import (
    VertexEmbeddingProvider,
    VertexGenerationProvider,
    create_vertex_client,
)
from folioaware.domain.answers import GenerationEvidence, GenerationRequest
from folioaware.domain.exceptions import (
    InvalidModelOutputError,
    ModelUnavailableError,
)
from folioaware.domain.knowledge import EmbeddingTaskType


class FakeModels:
    def __init__(
        self,
        *,
        embedding_response: object | None = None,
        generation_response: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.embedding_response = embedding_response
        self.generation_response = generation_response
        self.error = error
        self.embedding_call: dict[str, Any] | None = None
        self.generation_call: dict[str, Any] | None = None

    def embed_content(self, **kwargs: Any) -> object:
        self.embedding_call = kwargs
        if self.error is not None:
            raise self.error
        return self.embedding_response

    def generate_content(self, **kwargs: Any) -> object:
        self.generation_call = kwargs
        if self.error is not None:
            raise self.error
        return self.generation_response


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.models = models


class TextResponse:
    def __init__(self, text: str | None) -> None:
        self.text = text


def as_client(models: FakeModels) -> genai.Client:
    return cast(genai.Client, FakeClient(models))


def generation_request() -> GenerationRequest:
    return GenerationRequest(
        question="How was Atlas deployed?",
        knowledge_version="version-1",
        evidence=(
            GenerationEvidence(
                evidence_id="atlas:0001",
                content="Atlas was deployed to Cloud Run.",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("method", "task_type"),
    [
        ("embed_document", EmbeddingTaskType.RETRIEVAL_DOCUMENT),
        ("embed_query", EmbeddingTaskType.RETRIEVAL_QUERY),
    ],
)
def test_vertex_embeddings_use_explicit_task_and_disable_truncation(
    method: str, task_type: EmbeddingTaskType
) -> None:
    models = FakeModels(
        embedding_response=types.EmbedContentResponse(
            embeddings=[types.ContentEmbedding(values=[0.1, 0.2, 0.3])]
        )
    )
    provider = VertexEmbeddingProvider(
        client=as_client(models),
        model="embedding-model",
        dimensions=3,
    )

    embedding = getattr(provider, method)("Synthetic portfolio text")

    assert embedding.task_type is task_type
    assert embedding.values == (0.1, 0.2, 0.3)
    assert models.embedding_call is not None
    config = models.embedding_call["config"]
    assert isinstance(config, types.EmbedContentConfig)
    assert config.task_type == task_type.value
    assert config.auto_truncate is False
    assert config.output_dimensionality == 3


def test_vertex_embedding_rejects_wrong_vector_dimensions() -> None:
    models = FakeModels(
        embedding_response=types.EmbedContentResponse(
            embeddings=[types.ContentEmbedding(values=[0.1, 0.2])]
        )
    )
    provider = VertexEmbeddingProvider(
        client=as_client(models), model="embedding-model", dimensions=3
    )

    with pytest.raises(InvalidModelOutputError):
        provider.embed_query("question")


def test_vertex_generation_requests_structured_grounded_output() -> None:
    models = FakeModels(
        generation_response=TextResponse(
            '{"answer":"Atlas was deployed to Cloud Run.","evidenceIds":["atlas:0001"]}'
        )
    )
    provider = VertexGenerationProvider(
        client=as_client(models),
        model="generation-model",
        max_output_tokens=256,
    )

    candidate = provider.generate(generation_request())

    assert candidate.evidence_ids == ("atlas:0001",)
    assert models.generation_call is not None
    config = models.generation_call["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_mime_type == "application/json"
    assert config.tools is None
    assert config.temperature == 0
    assert "untrusted data" in str(config.system_instruction)


@pytest.mark.parametrize("text", [None, "not-json", '{"answer":"missing ids"}'])
def test_vertex_generation_rejects_invalid_output(text: str | None) -> None:
    provider = VertexGenerationProvider(
        client=as_client(FakeModels(generation_response=TextResponse(text))),
        model="generation-model",
        max_output_tokens=256,
    )

    with pytest.raises(InvalidModelOutputError):
        provider.generate(generation_request())


def test_vertex_errors_are_translated_without_vendor_details() -> None:
    provider = VertexEmbeddingProvider(
        client=as_client(FakeModels(error=RuntimeError("sensitive vendor detail"))),
        model="embedding-model",
        dimensions=3,
    )

    with pytest.raises(ModelUnavailableError) as error:
        provider.embed_document("content")

    assert "sensitive vendor detail" not in str(error.value)
    assert error.value.provider_error_type == "RuntimeError"
    assert error.value.provider_status is None


def test_vertex_error_preserves_only_safe_provider_diagnostics() -> None:
    provider_error = APIError(
        401,
        {"error": {"status": "UNAUTHENTICATED", "message": "sensitive detail"}},
    )
    provider = VertexEmbeddingProvider(
        client=as_client(FakeModels(error=provider_error)),
        model="embedding-model",
        dimensions=3,
    )

    with pytest.raises(ModelUnavailableError) as error:
        provider.embed_document("content")

    assert error.value.provider_error_type == "APIError"
    assert error.value.provider_status == "UNAUTHENTICATED"
    assert "sensitive detail" not in str(error.value)


def test_vertex_generation_errors_are_translated_without_vendor_details() -> None:
    provider = VertexGenerationProvider(
        client=as_client(FakeModels(error=RuntimeError("vendor detail"))),
        model="generation-model",
        max_output_tokens=256,
    )

    with pytest.raises(ModelUnavailableError) as error:
        provider.generate(generation_request())

    assert "vendor detail" not in str(error.value)


def test_vertex_client_factory_uses_stable_api_and_bounded_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = MagicMock(return_value=MagicMock())
    credentials = MagicMock(spec=Credentials)
    default_credentials = MagicMock(return_value=(credentials, "ambient-project"))
    monkeypatch.setattr(genai, "Client", constructor)
    monkeypatch.setattr(google.auth, "default", default_credentials)

    create_vertex_client(
        project="synthetic-project", location="global", timeout_seconds=12
    )

    kwargs = constructor.call_args.kwargs
    default_credentials.assert_called_once_with(
        scopes=("https://www.googleapis.com/auth/cloud-platform",)
    )
    assert kwargs["vertexai"] is True
    assert kwargs["credentials"] is credentials
    assert kwargs["project"] == "synthetic-project"
    http_options = kwargs["http_options"]
    assert isinstance(http_options, types.HttpOptions)
    assert http_options.api_version == "v1"
    assert http_options.timeout == 12_000
    assert http_options.retry_options is not None
    assert http_options.retry_options.attempts == 3


def test_vertex_client_factory_translates_adc_failure_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        google.auth,
        "default",
        MagicMock(side_effect=RuntimeError("sensitive credential detail")),
    )

    with pytest.raises(ModelUnavailableError) as error:
        create_vertex_client(
            project="synthetic-project", location="global", timeout_seconds=12
        )

    assert error.value.provider_error_type == "RuntimeError"
    assert error.value.provider_status is None
    assert "sensitive credential detail" not in str(error.value)
