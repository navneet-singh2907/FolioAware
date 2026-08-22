"""Capability-separated knowledge repository contracts."""

from collections.abc import Sequence
from typing import Protocol

from folioaware.domain.answers import Evidence
from folioaware.domain.knowledge import IndexVersion, KnowledgeChunk


class KnowledgeReadRepository(Protocol):
    def get_active_version(self) -> IndexVersion: ...

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        index_version: str,
        limit: int,
    ) -> Sequence[Evidence]: ...


class KnowledgeSyncRepository(Protocol):
    def get_active_version_or_none(self) -> IndexVersion | None: ...

    def get_active_chunks(self) -> Sequence[KnowledgeChunk]: ...

    def stage_candidate(
        self, version: IndexVersion, chunks: Sequence[KnowledgeChunk]
    ) -> None: ...

    def activate_candidate(
        self, *, candidate_version: str, expected_active_version: str | None
    ) -> None: ...

    def mark_candidate_failed(self, candidate_version: str) -> None: ...
