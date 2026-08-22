"""Privacy-reduced question persistence capability."""

from typing import Protocol

from folioaware.domain.telemetry import VisitorQuestion


class QuestionRepository(Protocol):
    def save(self, question: VisitorQuestion) -> None: ...
