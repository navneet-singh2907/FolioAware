"""Typed capabilities required by FolioAware use cases."""

from folioaware.ports.analytics import (
    InsightRepository,
    QuestionClassifier,
    QuestionTelemetryReader,
)
from folioaware.ports.sync_history import SyncHistoryRepository

__all__ = [
    "InsightRepository",
    "QuestionClassifier",
    "QuestionTelemetryReader",
    "SyncHistoryRepository",
]
