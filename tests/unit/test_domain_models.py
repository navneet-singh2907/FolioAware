from datetime import UTC, datetime, timedelta
from math import nan

import pytest
from pydantic import ValidationError

from folioaware.domain.answers import AnswerStatus, Citation
from folioaware.domain.knowledge import (
    ApprovedSource,
    Embedding,
    EmbeddingTaskType,
    SourceType,
)
from folioaware.domain.telemetry import VisitorQuestion


def test_approved_source_accepts_camel_case_contract() -> None:
    source = ApprovedSource.model_validate(
        {
            "schemaVersion": 1,
            "sourceId": "project-atlas",
            "sourceType": "project",
            "title": "Project Atlas",
            "citationUrl": "/projects/atlas",
            "content": "A synthetic project.",
            "tags": ["python"],
            "visibility": "public",
        }
    )

    assert source.source_type is SourceType.PROJECT
    assert source.source_id == "project-atlas"


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "http://example.test/project", "//evil.test", "/bad\\url"],
)
def test_citation_rejects_unsafe_url(url: str) -> None:
    with pytest.raises(ValidationError):
        Citation(source_id="project-atlas", title="Atlas", url=url)


def test_embedding_rejects_non_finite_or_wrong_dimensions() -> None:
    with pytest.raises(ValidationError):
        Embedding(
            values=(0.1, nan),
            model="local",
            task_type=EmbeddingTaskType.RETRIEVAL_DOCUMENT,
            dimensions=2,
        )
    with pytest.raises(ValidationError):
        Embedding(
            values=(0.1,),
            model="local",
            task_type=EmbeddingTaskType.RETRIEVAL_DOCUMENT,
            dimensions=2,
        )


def test_telemetry_expiry_must_follow_creation() -> None:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    with pytest.raises(ValidationError):
        VisitorQuestion(
            question_id="question-1",
            redacted_question="Does the portfolio mention Kafka?",
            answer_status=AnswerStatus.KNOWLEDGE_GAP,
            knowledge_version="version-1",
            created_at=now,
            expires_at=now - timedelta(seconds=1),
        )
