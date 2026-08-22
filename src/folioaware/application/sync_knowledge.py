"""Copy-on-write synchronization of approved sources."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from folioaware.domain.exceptions import SyncValidationError
from folioaware.domain.knowledge import (
    ApprovedSource,
    Embedding,
    EmbeddingTaskType,
    IndexStatus,
    IndexVersion,
    KnowledgeChunk,
    SyncResult,
    SyncStatus,
)
from folioaware.ports.embeddings import EmbeddingProvider
from folioaware.ports.knowledge_repository import KnowledgeSyncRepository
from folioaware.ports.runtime import Clock, IdentifierProvider


def canonical_source_hash(source: ApprovedSource) -> str:
    payload = source.model_dump(mode="json", by_alias=True)
    canonical = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def embedding_is_compatible(embedding: Embedding, provider: EmbeddingProvider) -> bool:
    return (
        embedding.model == provider.model
        and embedding.dimensions == provider.dimensions
        and embedding.task_type is EmbeddingTaskType.RETRIEVAL_DOCUMENT
    )


class SyncKnowledge:
    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        repository: KnowledgeSyncRepository,
        clock: Clock,
        identifiers: IdentifierProvider,
    ) -> None:
        self._embeddings = embeddings
        self._repository = repository
        self._clock = clock
        self._identifiers = identifiers

    def execute(
        self, *, sources: Sequence[ApprovedSource], git_commit: str
    ) -> SyncResult:
        started_at = self._clock.now()
        candidate_version = self._identifiers.new()
        sync_run_id = self._identifiers.new()
        previous = self._repository.get_active_version_or_none()
        previous_chunks = {
            (chunk.source_id, chunk.content_hash): chunk
            for chunk in self._repository.get_active_chunks()
        }
        previous_source_ids = {
            chunk.source_id for chunk in self._repository.get_active_chunks()
        }

        chunks: list[KnowledgeChunk] = []
        reused = 0
        for source in sources:
            content_hash = canonical_source_hash(source)
            existing = previous_chunks.get((source.source_id, content_hash))
            if existing is not None and embedding_is_compatible(
                existing.embedding, self._embeddings
            ):
                embedding = existing.embedding
                reused += 1
            else:
                embedding = self._embeddings.embed_document(source.content)

            chunk_id = f"{source.source_id}:0001:{content_hash[7:15]}"
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    source_id=source.source_id,
                    content=source.content,
                    content_hash=content_hash,
                    citation_title=source.title,
                    citation_url=source.citation_url,
                    visibility=source.visibility,
                    embedding=embedding,
                    index_version=candidate_version,
                )
            )

        source_ids = {source.source_id for source in sources}
        removed = len(previous_source_ids - source_ids)
        version = IndexVersion(
            index_version=candidate_version,
            git_commit=git_commit,
            status=IndexStatus.VALIDATING,
            source_count=len(sources),
            chunk_count=len(chunks),
            embedding_model=self._embeddings.model,
            embedding_dimensions=self._embeddings.dimensions,
            created_at=started_at,
        )
        self._repository.stage_candidate(version, chunks)

        try:
            self._validate_candidate(sources=sources, chunks=chunks)
            self._repository.activate_candidate(
                candidate_version=candidate_version,
                expected_active_version=(
                    previous.index_version if previous is not None else None
                ),
            )
        except Exception:
            self._repository.mark_candidate_failed(candidate_version)
            raise

        return SyncResult(
            sync_run_id=sync_run_id,
            candidate_index_version=candidate_version,
            git_commit=git_commit,
            status=SyncStatus.SUCCEEDED,
            sources_seen=len(sources),
            chunks_added=len(chunks) - reused,
            chunks_reused=reused,
            chunks_removed=removed,
            started_at=started_at,
            completed_at=self._clock.now(),
        )

    @staticmethod
    def _validate_candidate(
        *, sources: Sequence[ApprovedSource], chunks: Sequence[KnowledgeChunk]
    ) -> None:
        if not sources or len(sources) != len(chunks):
            raise SyncValidationError(
                "candidate must contain one chunk for every approved source"
            )
        if len({source.source_id for source in sources}) != len(sources):
            raise SyncValidationError("candidate contains duplicate source IDs")
