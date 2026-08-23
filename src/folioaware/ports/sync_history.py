"""Synchronization audit-history capability."""

from typing import Protocol

from folioaware.domain.knowledge import SyncResult


class SyncHistoryRepository(Protocol):
    def save(self, sync_run: SyncResult) -> None: ...
