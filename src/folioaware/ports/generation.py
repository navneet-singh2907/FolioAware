"""Bounded answer-generation capability."""

from typing import Protocol

from folioaware.domain.answers import AnswerCandidate, GenerationRequest


class GenerationProvider(Protocol):
    def generate(self, request: GenerationRequest) -> AnswerCandidate: ...
