from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from folioaware.adapters.local.embeddings import DeterministicEmbeddingProvider
from folioaware.adapters.local.repositories import InMemoryKnowledgeRepository
from folioaware.application.sync_knowledge import SyncKnowledge
from folioaware.domain.exceptions import SyncConflictError
from folioaware.domain.knowledge import IndexStatus, KnowledgeChunk
from folioaware.ingestion import load_approved_sources


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 22, tzinfo=UTC)

    def now(self) -> datetime:
        result = self.current
        self.current += timedelta(seconds=1)
        return result


class SequenceIdentifiers:
    def __init__(self, *values: str) -> None:
        self.values = iter(values)

    def new(self) -> str:
        return next(self.values)


class ConflictingRepository(InMemoryKnowledgeRepository):
    def activate_candidate(
        self, *, candidate_version: str, expected_active_version: str | None
    ) -> None:
        raise SyncConflictError("simulated concurrent activation")


def build_sync(
    repository: InMemoryKnowledgeRepository,
    embeddings: DeterministicEmbeddingProvider,
    identifiers: SequenceIdentifiers,
) -> SyncKnowledge:
    return SyncKnowledge(
        embeddings=embeddings,
        repository=repository,
        clock=FixedClock(),
        identifiers=identifiers,
    )


def test_sync_is_idempotent_and_reembeds_only_changed_content() -> None:
    sources = load_approved_sources(Path("examples/synthetic-portfolio"))
    repository = InMemoryKnowledgeRepository()
    embeddings = DeterministicEmbeddingProvider()
    sync = build_sync(
        repository,
        embeddings,
        SequenceIdentifiers(
            "version-1", "run-1", "version-2", "run-2", "version-3", "run-3"
        ),
    )

    first = sync.execute(sources=sources, git_commit="abcdef1")
    second = sync.execute(sources=sources, git_commit="abcdef2")
    changed_sources = (
        sources[0].model_copy(update={"content": f"{sources[0].content} Updated."}),
        *sources[1:],
    )
    third = sync.execute(sources=changed_sources, git_commit="abcdef3")

    assert first.chunks_added == 3
    assert first.chunks_reused == 0
    assert second.chunks_added == 0
    assert second.chunks_reused == 3
    assert third.chunks_added == 1
    assert third.chunks_reused == 2
    assert embeddings.document_calls == 4
    assert repository.get_active_version().index_version == "version-3"


def test_removed_source_is_absent_from_next_active_version() -> None:
    sources = load_approved_sources(Path("examples/synthetic-portfolio"))
    repository = InMemoryKnowledgeRepository()
    embeddings = DeterministicEmbeddingProvider()
    sync = build_sync(
        repository,
        embeddings,
        SequenceIdentifiers("version-1", "run-1", "version-2", "run-2"),
    )

    sync.execute(sources=sources, git_commit="abcdef1")
    result = sync.execute(sources=sources[:2], git_commit="abcdef2")

    assert result.chunks_removed == 1
    assert {chunk.source_id for chunk in repository.get_active_chunks()} == {
        "project-atlas",
        "project-lantern",
    }


def test_failed_activation_preserves_previous_active_version() -> None:
    sources = load_approved_sources(Path("examples/synthetic-portfolio"))
    healthy_repository = InMemoryKnowledgeRepository()
    embeddings = DeterministicEmbeddingProvider()
    initial_sync = build_sync(
        healthy_repository,
        embeddings,
        SequenceIdentifiers("version-1", "run-1"),
    )
    initial_sync.execute(sources=sources, git_commit="abcdef1")

    repository = ConflictingRepository()
    previous_version = healthy_repository.get_active_version()
    previous_chunks: Sequence[KnowledgeChunk] = healthy_repository.get_active_chunks()
    repository.stage_candidate(
        previous_version.model_copy(update={"status": IndexStatus.VALIDATING}),
        previous_chunks,
    )
    InMemoryKnowledgeRepository.activate_candidate(
        repository, candidate_version="version-1", expected_active_version=None
    )
    sync = build_sync(
        repository,
        embeddings,
        SequenceIdentifiers("version-2", "run-2"),
    )

    with pytest.raises(SyncConflictError):
        sync.execute(sources=sources, git_commit="abcdef2")

    assert repository.get_active_version().index_version == "version-1"
    assert repository.get_version("version-2").status is IndexStatus.FAILED  # type: ignore[union-attr]
