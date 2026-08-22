from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from google.cloud import firestore_v1
from google.cloud.firestore_v1.vector import Vector

from folioaware.adapters.google.firestore import (
    INDEX_VERSIONS,
    KNOWLEDGE_CHUNKS,
    SYSTEM,
    TOPIC_INSIGHTS,
    VECTOR_DISTANCE_FIELD,
    VISITOR_QUESTIONS,
    FirestoreInsightRepository,
    FirestoreKnowledgeRepository,
    FirestoreQuestionRepository,
    create_firestore_client,
)
from folioaware.domain.answers import AnswerStatus
from folioaware.domain.exceptions import (
    InsightsUnavailableError,
    KnowledgeUnavailableError,
    SyncConflictError,
    SyncValidationError,
)
from folioaware.domain.knowledge import (
    Embedding,
    EmbeddingTaskType,
    IndexStatus,
    IndexVersion,
    KnowledgeChunk,
)
from folioaware.domain.telemetry import SuggestedAction, TopicInsight, VisitorQuestion

NOW = datetime(2026, 8, 22, tzinfo=UTC)


def index_version(
    version: str = "version-1", status: IndexStatus = IndexStatus.ACTIVE
) -> IndexVersion:
    return IndexVersion(
        index_version=version,
        git_commit="abcdef1",
        status=status,
        source_count=1,
        chunk_count=1,
        embedding_model="embedding-model",
        embedding_dimensions=3,
        created_at=NOW,
        activated_at=NOW if status is IndexStatus.ACTIVE else None,
    )


def chunk(version: str = "version-1") -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id="project-atlas:0001:abcdef12",
        source_id="project-atlas",
        content="Atlas was deployed to Cloud Run.",
        content_hash=f"sha256:{'a' * 64}",
        citation_title="Project Atlas",
        citation_url="/projects/atlas",
        embedding=Embedding(
            values=(0.1, 0.2, 0.3),
            model="embedding-model",
            task_type=EmbeddingTaskType.RETRIEVAL_DOCUMENT,
            dimensions=3,
        ),
        index_version=version,
    )


def chunk_document(version: str = "version-1") -> dict[str, Any]:
    item = chunk(version)
    return {
        "chunk_id": item.chunk_id,
        "source_id": item.source_id,
        "content": item.content,
        "content_hash": item.content_hash,
        "citation_title": item.citation_title,
        "citation_url": item.citation_url,
        "evidence_status": item.evidence_status.value,
        "visibility": item.visibility.value,
        "embedding": Vector(item.embedding.values),
        "embedding_model": item.embedding.model,
        "embedding_task_type": item.embedding.task_type.value,
        "embedding_dimensions": item.embedding.dimensions,
        "index_version": item.index_version,
        "active": True,
    }


def snapshot(data: dict[str, Any] | None) -> MagicMock:
    result = MagicMock()
    result.exists = data is not None
    result.to_dict.return_value = data
    return result


def as_client(mock: MagicMock) -> firestore_v1.Client:
    return cast(firestore_v1.Client, mock)


def test_firestore_vector_search_filters_to_active_verified_public_version() -> None:
    client = MagicMock()
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot({"active_index_version": "version-1"})
    version_reference = MagicMock()
    version_reference.get.return_value = snapshot(
        index_version().model_dump(mode="python")
    )
    query = MagicMock()
    query.where.return_value = query
    vector_query = MagicMock()
    evidence_document = chunk_document()
    evidence_document[VECTOR_DISTANCE_FIELD] = 0.2
    vector_query.stream.return_value = [snapshot(evidence_document)]
    query.find_nearest.return_value = vector_query
    chunk_collection = MagicMock()
    chunk_collection.where.return_value = query
    pointer_collection = MagicMock()
    pointer_collection.document.return_value = pointer_reference
    version_collection = MagicMock()
    version_collection.document.return_value = version_reference

    collections = {
        SYSTEM: pointer_collection,
        INDEX_VERSIONS: version_collection,
        KNOWLEDGE_CHUNKS: chunk_collection,
    }
    client.collection.side_effect = collections.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=7
    )

    evidence = repository.search(
        query_vector=(0.1, 0.2, 0.3),
        index_version="version-1",
        limit=3,
    )

    assert evidence[0].source_id == "project-atlas"
    assert evidence[0].distance == 0.2
    assert chunk_collection.where.call_count == 1
    assert query.where.call_count == 3
    query.find_nearest.assert_called_once()
    vector_query.stream.assert_called_once_with(timeout=7)


def test_firestore_rejects_search_against_non_active_version() -> None:
    client = MagicMock()
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot({"active_index_version": "version-1"})
    version_reference = MagicMock()
    version_reference.get.return_value = snapshot(
        index_version().model_dump(mode="python")
    )
    pointer_collection = MagicMock()
    pointer_collection.document.return_value = pointer_reference
    version_collection = MagicMock()
    version_collection.document.return_value = version_reference
    client.collection.side_effect = {
        SYSTEM: pointer_collection,
        INDEX_VERSIONS: version_collection,
    }.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=7
    )

    with pytest.raises(KnowledgeUnavailableError, match="not active"):
        repository.search(
            query_vector=(0.1, 0.2, 0.3),
            index_version="retired-version",
            limit=3,
        )


def test_firestore_reports_missing_active_version() -> None:
    client = MagicMock()
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot(None)
    collection = MagicMock()
    collection.document.return_value = pointer_reference
    client.collection.return_value = collection
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=5
    )

    assert repository.get_active_version_or_none() is None
    with pytest.raises(KnowledgeUnavailableError, match="no active"):
        repository.get_active_version()


def test_firestore_rejects_malformed_or_inconsistent_active_pointer() -> None:
    for pointer_data in ({}, {"active_index_version": 42}):
        client = MagicMock()
        pointer_reference = MagicMock()
        pointer_reference.get.return_value = snapshot(pointer_data)
        collection = MagicMock()
        collection.document.return_value = pointer_reference
        client.collection.return_value = collection
        repository = FirestoreKnowledgeRepository(
            client=as_client(client), timeout_seconds=5
        )

        with pytest.raises(KnowledgeUnavailableError, match="pointer"):
            repository.get_active_version()

    client = MagicMock()
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot({"active_index_version": "version-1"})
    version_reference = MagicMock()
    version_reference.get.return_value = snapshot(
        index_version(status=IndexStatus.RETIRED).model_dump(mode="python")
    )
    pointer_collection = MagicMock()
    pointer_collection.document.return_value = pointer_reference
    version_collection = MagicMock()
    version_collection.document.return_value = version_reference
    client.collection.side_effect = {
        SYSTEM: pointer_collection,
        INDEX_VERSIONS: version_collection,
    }.__getitem__

    with pytest.raises(KnowledgeUnavailableError, match="inconsistent"):
        FirestoreKnowledgeRepository(
            client=as_client(client), timeout_seconds=5
        ).get_active_version()


def test_firestore_reads_active_chunks_through_version_filter() -> None:
    client = MagicMock()
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot({"active_index_version": "version-1"})
    version_reference = MagicMock()
    version_reference.get.return_value = snapshot(
        index_version().model_dump(mode="python")
    )
    pointer_collection = MagicMock()
    pointer_collection.document.return_value = pointer_reference
    version_collection = MagicMock()
    version_collection.document.return_value = version_reference
    query = MagicMock()
    query.stream.return_value = [snapshot(chunk_document())]
    chunk_collection = MagicMock()
    chunk_collection.where.return_value = query
    client.collection.side_effect = {
        SYSTEM: pointer_collection,
        INDEX_VERSIONS: version_collection,
        KNOWLEDGE_CHUNKS: chunk_collection,
    }.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=5
    )

    chunks = repository.get_active_chunks()

    assert chunks[0].source_id == "project-atlas"
    query.stream.assert_called_once_with(timeout=5)


def test_firestore_rejects_query_vector_with_wrong_dimensions() -> None:
    client = MagicMock()
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot({"active_index_version": "version-1"})
    version_reference = MagicMock()
    version_reference.get.return_value = snapshot(
        index_version().model_dump(mode="python")
    )
    pointer_collection = MagicMock()
    pointer_collection.document.return_value = pointer_reference
    version_collection = MagicMock()
    version_collection.document.return_value = version_reference
    client.collection.side_effect = {
        SYSTEM: pointer_collection,
        INDEX_VERSIONS: version_collection,
    }.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=5
    )

    with pytest.raises(KnowledgeUnavailableError, match="dimensions"):
        repository.search(query_vector=(0.1, 0.2), index_version="version-1", limit=3)


def test_firestore_stages_candidate_in_one_atomic_batch() -> None:
    client = MagicMock()
    batch = MagicMock()
    client.batch.return_value = batch
    chunk_collection = MagicMock()
    chunk_reference = MagicMock()
    chunk_collection.document.return_value = chunk_reference
    version_collection = MagicMock()
    version_reference = MagicMock()
    version_collection.document.return_value = version_reference
    client.collection.side_effect = {
        KNOWLEDGE_CHUNKS: chunk_collection,
        INDEX_VERSIONS: version_collection,
    }.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=9
    )
    candidate = index_version("version-2", IndexStatus.VALIDATING)

    repository.stage_candidate(candidate, [chunk("version-2")])

    batch.set.assert_called_once()
    stored_chunk = batch.set.call_args.args[1]
    assert isinstance(stored_chunk["embedding"], Vector)
    batch.create.assert_called_once_with(
        version_reference, candidate.model_dump(mode="python")
    )
    batch.commit.assert_called_once_with(timeout=9)


def test_firestore_safely_translates_candidate_staging_failure() -> None:
    client = MagicMock()
    batch = MagicMock()
    batch.commit.side_effect = RuntimeError("vendor detail")
    client.batch.return_value = batch
    chunk_collection = MagicMock()
    version_collection = MagicMock()
    client.collection.side_effect = {
        KNOWLEDGE_CHUNKS: chunk_collection,
        INDEX_VERSIONS: version_collection,
    }.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=5
    )

    with pytest.raises(SyncValidationError) as error:
        repository.stage_candidate(
            index_version("version-2", IndexStatus.VALIDATING),
            [chunk("version-2")],
        )

    assert "vendor detail" not in str(error.value)


def test_firestore_activation_compares_pointer_and_updates_in_transaction() -> None:
    client = MagicMock()
    transaction = MagicMock()
    client.transaction.return_value = transaction
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot({"active_index_version": "version-1"})
    candidate_reference = MagicMock()
    candidate_reference.get.return_value = snapshot(
        index_version("version-2", IndexStatus.VALIDATING).model_dump(mode="python")
    )
    previous_reference = MagicMock()
    pointer_collection = MagicMock()
    pointer_collection.document.return_value = pointer_reference
    version_collection = MagicMock()
    version_collection.document.side_effect = [
        candidate_reference,
        previous_reference,
    ]
    client.collection.side_effect = {
        SYSTEM: pointer_collection,
        INDEX_VERSIONS: version_collection,
    }.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=11
    )

    repository.activate_candidate(
        candidate_version="version-2", expected_active_version="version-1"
    )

    transaction.update.assert_any_call(
        previous_reference, {"status": IndexStatus.RETIRED.value}
    )
    transaction.update.assert_any_call(
        candidate_reference,
        {"status": IndexStatus.ACTIVE.value, "activated_at": NOW},
    )
    transaction.set.assert_called_once_with(
        pointer_reference, {"active_index_version": "version-2"}
    )
    transaction.commit.assert_called_once_with(timeout=11)


def test_firestore_activation_rejects_stale_expected_pointer() -> None:
    client = MagicMock()
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot(
        {"active_index_version": "newer-version"}
    )
    pointer_collection = MagicMock()
    pointer_collection.document.return_value = pointer_reference
    version_collection = MagicMock()
    client.collection.side_effect = {
        SYSTEM: pointer_collection,
        INDEX_VERSIONS: version_collection,
    }.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=5
    )

    with pytest.raises(SyncConflictError):
        repository.activate_candidate(
            candidate_version="version-2", expected_active_version="version-1"
        )


def test_firestore_activation_rejects_candidate_not_in_validating_state() -> None:
    client = MagicMock()
    pointer_reference = MagicMock()
    pointer_reference.get.return_value = snapshot(None)
    candidate_reference = MagicMock()
    candidate_reference.get.return_value = snapshot(
        index_version("version-2", IndexStatus.FAILED).model_dump(mode="python")
    )
    pointer_collection = MagicMock()
    pointer_collection.document.return_value = pointer_reference
    version_collection = MagicMock()
    version_collection.document.return_value = candidate_reference
    client.collection.side_effect = {
        SYSTEM: pointer_collection,
        INDEX_VERSIONS: version_collection,
    }.__getitem__
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=5
    )

    with pytest.raises(SyncValidationError, match="not ready"):
        repository.activate_candidate(
            candidate_version="version-2", expected_active_version=None
        )


def test_firestore_candidate_batch_limit_fails_before_any_write() -> None:
    repository = FirestoreKnowledgeRepository(
        client=as_client(MagicMock()), timeout_seconds=5
    )
    candidate = index_version("version-2", IndexStatus.VALIDATING)

    with pytest.raises(SyncValidationError, match="exceeds"):
        repository.stage_candidate(candidate, [chunk("version-2")] * 500)


def test_firestore_rejects_invalid_candidate_before_writing() -> None:
    client = MagicMock()
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=5
    )

    with pytest.raises(SyncValidationError, match="validating"):
        repository.stage_candidate(index_version(), [chunk()])
    with pytest.raises(SyncValidationError, match="version mismatch"):
        repository.stage_candidate(
            index_version("version-2", IndexStatus.VALIDATING), [chunk("version-3")]
        )
    client.batch.assert_not_called()


def test_firestore_marks_failed_candidate_without_exposing_vendor_error() -> None:
    client = MagicMock()
    reference = MagicMock()
    collection = MagicMock()
    collection.document.return_value = reference
    client.collection.return_value = collection
    repository = FirestoreKnowledgeRepository(
        client=as_client(client), timeout_seconds=4
    )

    repository.mark_candidate_failed("version-2")

    reference.update.assert_called_once_with(
        {"status": IndexStatus.FAILED.value}, timeout=4
    )
    reference.update.side_effect = RuntimeError("vendor detail")
    with pytest.raises(SyncValidationError) as error:
        repository.mark_candidate_failed("version-2")
    assert "vendor detail" not in str(error.value)


def test_firestore_question_document_contains_only_privacy_reduced_contract() -> None:
    client = MagicMock()
    reference = MagicMock()
    collection = MagicMock()
    collection.document.return_value = reference
    client.collection.return_value = collection
    repository = FirestoreQuestionRepository(
        client=as_client(client), timeout_seconds=6
    )
    question = VisitorQuestion(
        question_id="request/unsafe-path",
        redacted_question="Email [REDACTED_EMAIL] about FastAPI",
        session_hash=f"hmac-sha256:key:{'a' * 64}",
        answer_status=AnswerStatus.ANSWERED,
        knowledge_version="version-1",
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )

    repository.save(question)

    client.collection.assert_called_once_with(VISITOR_QUESTIONS)
    persisted_id = collection.document.call_args.args[0]
    assert persisted_id != question.question_id
    assert "/" not in persisted_id
    document = reference.create.call_args.args[0]
    assert document["redacted_question"] == question.redacted_question
    assert "answer" not in document
    assert "raw_session_id" not in document
    reference.create.assert_called_once_with(document, timeout=6)


def test_firestore_question_failure_is_safely_translated() -> None:
    client = MagicMock()
    reference = MagicMock()
    reference.create.side_effect = RuntimeError("vendor detail")
    collection = MagicMock()
    collection.document.return_value = reference
    client.collection.return_value = collection
    repository = FirestoreQuestionRepository(
        client=as_client(client), timeout_seconds=6
    )
    question = VisitorQuestion(
        question_id="request-1",
        redacted_question="Question",
        answer_status=AnswerStatus.KNOWLEDGE_GAP,
        knowledge_version="version-1",
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )

    with pytest.raises(RuntimeError) as error:
        repository.save(question)

    assert "vendor detail" not in str(error.value)


def test_firestore_reads_question_telemetry_only_inside_period() -> None:
    client = MagicMock()
    query = MagicMock()
    query.where.return_value = query
    stored = VisitorQuestion(
        question_id="request-1",
        redacted_question="Have they used Kafka?",
        answer_status=AnswerStatus.KNOWLEDGE_GAP,
        knowledge_version="version-1",
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )
    query.stream.return_value = [snapshot(stored.model_dump(mode="python"))]
    collection = MagicMock()
    collection.where.return_value = query
    client.collection.return_value = collection
    repository = FirestoreQuestionRepository(
        client=as_client(client), timeout_seconds=8
    )

    records = repository.list_between(
        period_start=NOW - timedelta(days=1), period_end=NOW + timedelta(days=1)
    )

    assert records == (stored,)
    client.collection.assert_called_once_with(VISITOR_QUESTIONS)
    assert query.where.call_count == 1
    query.stream.assert_called_once_with(timeout=8)


def test_firestore_safely_translates_question_telemetry_read_failure() -> None:
    client = MagicMock()
    collection = MagicMock()
    collection.where.side_effect = RuntimeError("vendor detail")
    client.collection.return_value = collection
    repository = FirestoreQuestionRepository(
        client=as_client(client), timeout_seconds=8
    )

    with pytest.raises(InsightsUnavailableError) as error:
        repository.list_between(period_start=NOW - timedelta(days=1), period_end=NOW)

    assert "vendor detail" not in str(error.value)


def test_firestore_replaces_period_insights_in_one_batch() -> None:
    client = MagicMock()
    batch = MagicMock()
    client.batch.return_value = batch
    stale_snapshot = MagicMock()
    stale_snapshot.id = "stale-document"
    query = MagicMock()
    query.where.return_value = query
    query.stream.return_value = [stale_snapshot]
    reference = MagicMock()
    collection = MagicMock()
    collection.where.return_value = query
    collection.document.return_value = reference
    client.collection.return_value = collection
    repository = FirestoreInsightRepository(client=as_client(client), timeout_seconds=9)
    insight = TopicInsight(
        insight_id="apache-kafka:period",
        topic="apache-kafka",
        period_start=NOW,
        period_end=NOW + timedelta(days=7),
        distinct_session_count=2,
        question_count=3,
        skill_verification_count=3,
        knowledge_gap_count=3,
        suggested_action=SuggestedAction.BUILD_PROJECT,
        created_at=NOW,
    )

    repository.replace_period(
        period_start=insight.period_start,
        period_end=insight.period_end,
        insights=(insight,),
    )

    client.collection.assert_called_once_with(TOPIC_INSIGHTS)
    batch.delete.assert_called_once_with(stale_snapshot.reference)
    batch.set.assert_called_once_with(reference, insight.model_dump(mode="python"))
    batch.commit.assert_called_once_with(timeout=9)


def test_firestore_client_factory_passes_explicit_single_tenant_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(firestore_v1, "Client", constructor)

    create_firestore_client(project="synthetic-project", database="portfolio")

    constructor.assert_called_once_with(
        project="synthetic-project", database="portfolio"
    )
