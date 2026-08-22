"""Firestore repositories with explicit collection and trust boundaries."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any, cast

from google.api_core.exceptions import Aborted, Conflict
from google.cloud import firestore_v1
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from pydantic import ValidationError

from folioaware.domain.answers import Evidence
from folioaware.domain.exceptions import (
    FolioAwareError,
    KnowledgeUnavailableError,
    SyncConflictError,
    SyncValidationError,
)
from folioaware.domain.knowledge import (
    Embedding,
    IndexStatus,
    IndexVersion,
    KnowledgeChunk,
)
from folioaware.domain.telemetry import VisitorQuestion

KNOWLEDGE_CHUNKS = "knowledge_chunks"
INDEX_VERSIONS = "index_versions"
VISITOR_QUESTIONS = "visitor_questions"
SYSTEM = "system"
KNOWLEDGE_POINTER = "knowledge"
VECTOR_DISTANCE_FIELD = "vector_distance"
MAX_BATCH_CHUNKS = 499


def create_firestore_client(*, project: str, database: str) -> firestore_v1.Client:
    """Create a Firestore client using Application Default Credentials."""
    return firestore_v1.Client(project=project, database=database)


def _safe_document_id(namespace: str, value: str) -> str:
    digest = hashlib.sha256(f"{namespace}\0{value}".encode()).hexdigest()
    return digest


def _version_document_id(index_version: str) -> str:
    return _safe_document_id("index-version", index_version)


def _chunk_document_id(chunk: KnowledgeChunk) -> str:
    return _safe_document_id(
        "knowledge-chunk", f"{chunk.index_version}\0{chunk.chunk_id}"
    )


def _question_document_id(question_id: str) -> str:
    return _safe_document_id("visitor-question", question_id)


def _index_to_document(version: IndexVersion) -> dict[str, Any]:
    return version.model_dump(mode="python", by_alias=False)


def _document_to_index(data: Mapping[str, Any]) -> IndexVersion:
    return IndexVersion.model_validate(data)


def _chunk_to_document(chunk: KnowledgeChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "content": chunk.content,
        "content_hash": chunk.content_hash,
        "citation_title": chunk.citation_title,
        "citation_url": chunk.citation_url,
        "evidence_status": chunk.evidence_status.value,
        "visibility": chunk.visibility.value,
        "embedding": Vector(chunk.embedding.values),
        "embedding_model": chunk.embedding.model,
        "embedding_task_type": chunk.embedding.task_type.value,
        "embedding_dimensions": chunk.embedding.dimensions,
        "index_version": chunk.index_version,
        "active": chunk.active,
    }


def _document_to_chunk(data: Mapping[str, Any]) -> KnowledgeChunk:
    embedding_values = data.get("embedding")
    if not isinstance(embedding_values, Sequence) or isinstance(
        embedding_values, (str, bytes)
    ):
        raise ValueError("stored embedding is not a vector")
    return KnowledgeChunk.model_validate(
        {
            "chunk_id": data.get("chunk_id"),
            "source_id": data.get("source_id"),
            "content": data.get("content"),
            "content_hash": data.get("content_hash"),
            "citation_title": data.get("citation_title"),
            "citation_url": data.get("citation_url"),
            "evidence_status": data.get("evidence_status"),
            "visibility": data.get("visibility"),
            "embedding": Embedding.model_validate(
                {
                    "values": tuple(float(value) for value in embedding_values),
                    "model": data.get("embedding_model"),
                    "task_type": data.get("embedding_task_type"),
                    "dimensions": data.get("embedding_dimensions"),
                }
            ),
            "index_version": data.get("index_version"),
            "active": data.get("active"),
        }
    )


def _snapshot_data(snapshot: Any) -> Mapping[str, Any]:
    data = snapshot.to_dict()
    if not snapshot.exists or not isinstance(data, Mapping):
        raise KnowledgeUnavailableError("required Firestore document is missing")
    return data


class FirestoreKnowledgeRepository:
    def __init__(self, *, client: firestore_v1.Client, timeout_seconds: int) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    def get_active_version(self) -> IndexVersion:
        version = self.get_active_version_or_none()
        if version is None:
            raise KnowledgeUnavailableError("no active knowledge version")
        return version

    def get_active_version_or_none(self) -> IndexVersion | None:
        try:
            pointer = self._client.collection(SYSTEM).document(KNOWLEDGE_POINTER)
            snapshot = pointer.get(timeout=self._timeout_seconds)
            if not snapshot.exists:
                return None
            pointer_data = snapshot.to_dict()
            if not isinstance(pointer_data, Mapping):
                raise KnowledgeUnavailableError("active pointer is invalid")
            index_version = pointer_data.get("active_index_version")
            if not isinstance(index_version, str):
                raise KnowledgeUnavailableError("active pointer is invalid")
            version_snapshot = (
                self._client.collection(INDEX_VERSIONS)
                .document(_version_document_id(index_version))
                .get(timeout=self._timeout_seconds)
            )
            version = _document_to_index(_snapshot_data(version_snapshot))
            if (
                version.index_version != index_version
                or version.status is not IndexStatus.ACTIVE
            ):
                raise KnowledgeUnavailableError("active version is inconsistent")
            return version
        except FolioAwareError:
            raise
        except (ValidationError, ValueError, TypeError) as error:
            raise KnowledgeUnavailableError("active version is invalid") from error
        except Exception as error:
            raise KnowledgeUnavailableError("active version read failed") from error

    def get_active_chunks(self) -> Sequence[KnowledgeChunk]:
        version = self.get_active_version_or_none()
        if version is None:
            return ()
        try:
            snapshots = (
                self._client.collection(KNOWLEDGE_CHUNKS)
                .where(filter=FieldFilter("index_version", "==", version.index_version))
                .stream(timeout=self._timeout_seconds)
            )
            return tuple(
                _document_to_chunk(_snapshot_data(snapshot)) for snapshot in snapshots
            )
        except FolioAwareError:
            raise
        except Exception as error:
            raise KnowledgeUnavailableError("active chunks read failed") from error

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        index_version: str,
        limit: int,
    ) -> Sequence[Evidence]:
        active = self.get_active_version()
        if active.index_version != index_version:
            raise KnowledgeUnavailableError("requested knowledge version is not active")
        if len(query_vector) != active.embedding_dimensions:
            raise KnowledgeUnavailableError(
                "query embedding dimensions are incompatible"
            )
        try:
            collection = self._client.collection(KNOWLEDGE_CHUNKS)
            query = collection.where(
                filter=FieldFilter("index_version", "==", index_version)
            )
            query = query.where(filter=FieldFilter("active", "==", True))
            query = query.where(filter=FieldFilter("visibility", "==", "public"))
            query = query.where(filter=FieldFilter("evidence_status", "==", "verified"))
            vector_query = cast(Any, query).find_nearest(
                vector_field="embedding",
                query_vector=Vector(query_vector),
                limit=limit,
                distance_measure=DistanceMeasure.COSINE,
                distance_result_field=VECTOR_DISTANCE_FIELD,
            )
            snapshots = vector_query.stream(timeout=self._timeout_seconds)
            evidence: list[Evidence] = []
            for snapshot in snapshots:
                data = _snapshot_data(snapshot)
                chunk = _document_to_chunk(data)
                distance = data.get(VECTOR_DISTANCE_FIELD)
                if not isinstance(distance, int | float):
                    raise ValueError("vector result omitted distance")
                if chunk.index_version != index_version:
                    raise ValueError("vector result has wrong index version")
                evidence.append(
                    Evidence(
                        evidence_id=chunk.chunk_id,
                        source_id=chunk.source_id,
                        content=chunk.content,
                        citation_title=chunk.citation_title,
                        citation_url=chunk.citation_url,
                        index_version=chunk.index_version,
                        distance=float(distance),
                    )
                )
            return tuple(evidence)
        except FolioAwareError:
            raise
        except Exception as error:
            raise KnowledgeUnavailableError("vector search failed") from error

    def stage_candidate(
        self, version: IndexVersion, chunks: Sequence[KnowledgeChunk]
    ) -> None:
        if version.status is not IndexStatus.VALIDATING:
            raise SyncValidationError("candidate must be validating before staging")
        if len(chunks) > MAX_BATCH_CHUNKS:
            raise SyncValidationError("candidate exceeds one Firestore batch")
        if any(chunk.index_version != version.index_version for chunk in chunks):
            raise SyncValidationError("candidate chunk version mismatch")
        try:
            batch = self._client.batch()
            for chunk in chunks:
                reference = self._client.collection(KNOWLEDGE_CHUNKS).document(
                    _chunk_document_id(chunk)
                )
                batch.set(reference, _chunk_to_document(chunk))
            version_reference = self._client.collection(INDEX_VERSIONS).document(
                _version_document_id(version.index_version)
            )
            batch.create(version_reference, _index_to_document(version))
            batch.commit(timeout=self._timeout_seconds)
        except FolioAwareError:
            raise
        except Exception as error:
            raise SyncValidationError("candidate staging failed") from error

    def activate_candidate(
        self, *, candidate_version: str, expected_active_version: str | None
    ) -> None:
        transaction = self._client.transaction(max_attempts=1)
        pointer_reference = self._client.collection(SYSTEM).document(KNOWLEDGE_POINTER)
        candidate_reference = self._client.collection(INDEX_VERSIONS).document(
            _version_document_id(candidate_version)
        )
        try:
            pointer_snapshot = pointer_reference.get(
                transaction=transaction, timeout=self._timeout_seconds
            )
            if pointer_snapshot.exists:
                raw_pointer = pointer_snapshot.to_dict()
                if not isinstance(raw_pointer, Mapping):
                    raise SyncValidationError("active pointer is invalid")
                pointer_data = raw_pointer
            else:
                pointer_data = {}
            current = pointer_data.get("active_index_version")
            if current != expected_active_version:
                raise SyncConflictError("active version changed during synchronization")
            candidate_snapshot = candidate_reference.get(
                transaction=transaction, timeout=self._timeout_seconds
            )
            candidate = _document_to_index(_snapshot_data(candidate_snapshot))
            if (
                candidate.index_version != candidate_version
                or candidate.status is not IndexStatus.VALIDATING
            ):
                raise SyncValidationError("candidate is not ready for activation")

            if current is not None:
                previous_reference = self._client.collection(INDEX_VERSIONS).document(
                    _version_document_id(current)
                )
                transaction.update(
                    previous_reference, {"status": IndexStatus.RETIRED.value}
                )
            transaction.update(
                candidate_reference,
                {
                    "status": IndexStatus.ACTIVE.value,
                    "activated_at": candidate.created_at,
                },
            )
            transaction.set(
                pointer_reference,
                {"active_index_version": candidate_version},
            )
            transaction.commit(timeout=self._timeout_seconds)
        except SyncConflictError:
            raise
        except (Aborted, Conflict) as error:
            raise SyncConflictError("candidate activation conflicted") from error
        except FolioAwareError:
            raise
        except Exception as error:
            raise SyncValidationError("candidate activation failed") from error

    def mark_candidate_failed(self, candidate_version: str) -> None:
        try:
            self._client.collection(INDEX_VERSIONS).document(
                _version_document_id(candidate_version)
            ).update(
                {"status": IndexStatus.FAILED.value},
                timeout=self._timeout_seconds,
            )
        except Exception as error:
            raise SyncValidationError("failed candidate could not be marked") from error


class FirestoreQuestionRepository:
    def __init__(self, *, client: firestore_v1.Client, timeout_seconds: int) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    def save(self, question: VisitorQuestion) -> None:
        document = question.model_dump(mode="python", by_alias=False)
        try:
            self._client.collection(VISITOR_QUESTIONS).document(
                _question_document_id(question.question_id)
            ).create(document, timeout=self._timeout_seconds)
        except Exception as error:
            raise RuntimeError("question persistence failed") from error
