"""Typed capabilities required by FolioAware use cases."""

from folioaware.ports.analytics import (
    InsightRepository,
    QuestionClassifier,
    QuestionTelemetryReader,
)

__all__ = ["InsightRepository", "QuestionClassifier", "QuestionTelemetryReader"]
