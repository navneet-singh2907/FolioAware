from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from folioaware.adapters.local.embeddings import DeterministicEmbeddingProvider
from folioaware.adapters.local.repositories import (
    InMemoryKnowledgeRepository,
    InMemorySyncHistoryRepository,
)
from folioaware.application.sync_knowledge import SyncKnowledge, _sync_error_code
from folioaware.domain.exceptions import (
    KnowledgeUnavailableError,
    ModelUnavailableError,
    SyncConflictError,
    SyncValidationError,
)
from folioaware.domain.knowledge import IndexStatus, KnowledgeChunk, SyncResult
from folioaware.ingestion import load_approved_sources
from folioaware.ports.sync_history import SyncHistoryRepository


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


class RejectingHistory:
    def save(self, sync_run: SyncResult) -> None:
        raise SyncValidationError("audit unavailable")


class TerminalRejectingHistory:
    def __init__(self) -> None:
        self.calls = 0

    def save(self, sync_run: SyncResult) -> None:
        self.calls += 1
        if self.calls > 1:
            raise SyncValidationError("terminal audit unavailable")


def build_sync(
    repository: InMemoryKnowledgeRepository,
    embeddings: DeterministicEmbeddingProvider,
    identifiers: SequenceIdentifiers,
    history: SyncHistoryRepository | None = None,
) -> SyncKnowledge:
    return SyncKnowledge(
        embeddings=embeddings,
        repository=repository,
        history=history or InMemorySyncHistoryRepository(),
        clock=FixedClock(),
        identifiers=identifiers,
    )


def test_sync_is_idempotent_and_reembeds_only_changed_content() -> None:
    sources = load_approved_sources(Path("examples/synthetic-portfolio"))
    repository = InMemoryKnowledgeRepository()
    embeddings = DeterministicEmbeddingProvider()
    history = InMemorySyncHistoryRepository()
    sync = build_sync(
        repository,
        embeddings,
        SequenceIdentifiers(
            "version-1", "run-1", "version-2", "run-2", "version-3", "run-3"
        ),
        history,
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
    assert history.records["run-1"].status.value == "succeeded"
    assert history.records["run-3"].chunks_added == 1


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
    history = InMemorySyncHistoryRepository()
    sync = build_sync(
        repository,
        embeddings,
        SequenceIdentifiers("version-2", "run-2"),
        history,
    )

    with pytest.raises(SyncConflictError):
        sync.execute(sources=sources, git_commit="abcdef2")

    assert repository.get_active_version().index_version == "version-1"
    assert repository.get_version("version-2").status is IndexStatus.FAILED  # type: ignore[union-attr]
    assert history.records["run-2"].status.value == "failed"
    assert history.records["run-2"].error_code == "SYNC_CONFLICT"


def test_initial_history_failure_prevents_embedding_and_knowledge_writes() -> None:
    sources = load_approved_sources(Path("examples/synthetic-portfolio"))
    repository = InMemoryKnowledgeRepository()
    embeddings = DeterministicEmbeddingProvider()
    sync = build_sync(
        repository,
        embeddings,
        SequenceIdentifiers("version-1", "run-1"),
        RejectingHistory(),
    )

    with pytest.raises(SyncValidationError, match="audit unavailable"):
        sync.execute(sources=sources, git_commit="abcdef1")

    assert embeddings.document_calls == 0
    assert repository.get_active_version_or_none() is None


def test_terminal_history_failure_does_not_undo_activation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sources = load_approved_sources(Path("examples/synthetic-portfolio"))
    repository = InMemoryKnowledgeRepository()
    history = TerminalRejectingHistory()
    sync = build_sync(
        repository,
        DeterministicEmbeddingProvider(),
        SequenceIdentifiers("version-1", "run-1"),
        history,
    )

    result = sync.execute(sources=sources, git_commit="abcdef1")

    assert result.status.value == "succeeded"
    assert repository.get_active_version().index_version == "version-1"
    assert history.calls == 2
    assert "terminal sync history update failed" in caplog.text


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ModelUnavailableError(), "EMBEDDING_UNAVAILABLE"),
        (KnowledgeUnavailableError(), "KNOWLEDGE_UNAVAILABLE"),
        (SyncValidationError(), "SYNC_VALIDATION_FAILED"),
        (RuntimeError(), "INTERNAL_SYNC_ERROR"),
    ],
)
def test_sync_history_uses_stable_sanitized_error_codes(
    error: Exception, expected: str
) -> None:
    assert _sync_error_code(error) == expected
