"""Explainable topic and intent rules; no model calls and no fact creation."""

import re

from folioaware.domain.telemetry import (
    ClassifiedQuestion,
    QuestionIntent,
    TopicRule,
)

_SKILL_MARKERS = (
    "experience with",
    "worked with",
    "work with",
    "used ",
    "use ",
    "know ",
    "familiar with",
    "skilled in",
    "expert in",
)
_ARCHITECTURE_MARKERS = ("architecture", "architected", "system design", "stack")
_PROJECT_MARKERS = ("project", "built", "created", "developed", "implemented")
_AVAILABILITY_MARKERS = ("available", "availability", "open to work", "hire")


class DeterministicQuestionClassifier:
    def __init__(self, rules: tuple[TopicRule, ...]) -> None:
        self._rules = rules

    def classify(self, question: str) -> ClassifiedQuestion:
        normalized = " ".join(question.casefold().split())
        topics = tuple(
            rule.topic
            for rule in self._rules
            if any(self._contains(normalized, alias) for alias in rule.aliases)
        )
        return ClassifiedQuestion(
            intent=self._intent(normalized, has_topic=bool(topics)),
            topics=topics,
        )

    @staticmethod
    def _contains(question: str, alias: str) -> bool:
        return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", question) is not None

    @staticmethod
    def _intent(question: str, *, has_topic: bool) -> QuestionIntent:
        if has_topic and any(marker in question for marker in _SKILL_MARKERS):
            return QuestionIntent.SKILL_VERIFICATION
        if any(marker in question for marker in _ARCHITECTURE_MARKERS):
            return QuestionIntent.ARCHITECTURE
        if any(marker in question for marker in _PROJECT_MARKERS):
            return QuestionIntent.PROJECT_EXPERIENCE
        if any(marker in question for marker in _AVAILABILITY_MARKERS):
            return QuestionIntent.AVAILABILITY
        return QuestionIntent.UNKNOWN
