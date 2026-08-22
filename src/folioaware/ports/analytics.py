"""Capabilities for privacy-safe telemetry analysis and insight persistence."""

from datetime import datetime
from typing import Protocol

from folioaware.domain.telemetry import (
    ClassifiedQuestion,
    TopicInsight,
    VisitorQuestion,
)


class QuestionTelemetryReader(Protocol):
    def list_between(
        self, *, period_start: datetime, period_end: datetime
    ) -> tuple[VisitorQuestion, ...]: ...


class QuestionClassifier(Protocol):
    def classify(self, question: str) -> ClassifiedQuestion: ...


class InsightRepository(Protocol):
    def replace_period(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
        insights: tuple[TopicInsight, ...],
    ) -> None: ...
