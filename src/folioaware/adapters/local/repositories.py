"""In-memory repositories with production-equivalent capability boundaries."""

from __future__ import annotations

import math
from collections.abc import Sequence

from folioaware.domain.answers import Evidence
from folioaware.domain.exceptions import (
    KnowledgeUnavailableError,
    SyncConflictError,
    SyncValidationError,
)
from folioaware.domain.knowledge import (
    EvidenceStatus,
    IndexStatus,
    IndexVersion,
    KnowledgeChunk,
    Visibility,
)
from folioaware.domain.telemetry import VisitorQuestion


def _cosine_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise KnowledgeUnavailableError("embedding dimensions are incompatible")
    left_magnitude = math.sqrt(sum(value * value for value in left))
    right_magnitude = math.sqrt(sum(value * value for value in right))
    if not left_magnitude or not right_magnitude:
        return 1.0
    similarity = sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_magnitude * right_magnitude
    )
    return max(0.0, min(2.0, 1.0 - similarity))


class InMemoryKnowledgeRepository:
    """Copy-on-write local knowledge repository used by the MVP."""

    def __init__(self) -> None:
        self._versions: dict[str, IndexVersion] = {}
        self._chunks: dict[str, tuple[KnowledgeChunk, ...]] = {}
        self._active_version: str | None = None

    def get_active_version(self) -> IndexVersion:
        active = self.get_active_version_or_none()
        if active is None:
            raise KnowledgeUnavailableError("no active knowledge version")
        return active

    def get_active_version_or_none(self) -> IndexVersion | None:
        if self._active_version is None:
            return None
        return self._versions[self._active_version]

    def get_active_chunks(self) -> Sequence[KnowledgeChunk]:
        if self._active_version is None:
            return ()
        return self._chunks[self._active_version]

    def stage_candidate(
        self, version: IndexVersion, chunks: Sequence[KnowledgeChunk]
    ) -> None:
        if version.status is not IndexStatus.VALIDATING:
            raise SyncValidationError("candidate must be validating before staging")
        if version.index_version in self._versions:
            raise SyncValidationError("candidate version already exists")
        if any(chunk.index_version != version.index_version for chunk in chunks):
            raise SyncValidationError("candidate chunk version mismatch")
        self._versions[version.index_version] = version
        self._chunks[version.index_version] = tuple(chunks)

    def activate_candidate(
        self, *, candidate_version: str, expected_active_version: str | None
    ) -> None:
        if self._active_version != expected_active_version:
            raise SyncConflictError("active version changed during synchronization")
        candidate = self._versions.get(candidate_version)
        if candidate is None or candidate.status is not IndexStatus.VALIDATING:
            raise SyncValidationError("candidate is not ready for activation")

        if self._active_version is not None:
            previous = self._versions[self._active_version]
            self._versions[self._active_version] = previous.model_copy(
                update={"status": IndexStatus.RETIRED}
            )
        self._versions[candidate_version] = candidate.model_copy(
            update={"status": IndexStatus.ACTIVE, "activated_at": candidate.created_at}
        )
        self._active_version = candidate_version

    def mark_candidate_failed(self, candidate_version: str) -> None:
        candidate = self._versions.get(candidate_version)
        if candidate is not None and candidate.status is IndexStatus.VALIDATING:
            self._versions[candidate_version] = candidate.model_copy(
                update={"status": IndexStatus.FAILED}
            )

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        index_version: str,
        limit: int,
    ) -> Sequence[Evidence]:
        if self._active_version != index_version:
            raise KnowledgeUnavailableError("requested knowledge version is not active")
        chunks = self._chunks.get(index_version, ())
        evidence = [
            Evidence(
                evidence_id=chunk.chunk_id,
                source_id=chunk.source_id,
                content=chunk.content,
                citation_title=chunk.citation_title,
                citation_url=chunk.citation_url,
                index_version=chunk.index_version,
                distance=_cosine_distance(query_vector, chunk.embedding.values),
            )
            for chunk in chunks
            if chunk.active
            and chunk.visibility is Visibility.PUBLIC
            and chunk.evidence_status is EvidenceStatus.VERIFIED
        ]
        return tuple(sorted(evidence, key=lambda item: item.distance)[:limit])

    def get_version(self, index_version: str) -> IndexVersion | None:
        """Inspection helper for deterministic tests, not an application port."""
        return self._versions.get(index_version)


class InMemoryQuestionRepository:
    def __init__(self) -> None:
        self.records: list[VisitorQuestion] = []

    def save(self, question: VisitorQuestion) -> None:
        self.records.append(question)
