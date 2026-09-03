"""Strict contracts for versioned, synthetic RAG evaluation suites."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from folioaware.domain.base import DomainModel
from folioaware.domain.knowledge import SOURCE_ID_PATTERN

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_evaluation_text(value: str) -> str:
    """Normalize whitespace without changing evaluation meaning."""
    return " ".join(value.split())


class EvaluationStatus(StrEnum):
    ANSWERED = "answered"
    KNOWLEDGE_GAP = "knowledge_gap"


class EvaluationTag(StrEnum):
    ANSWERABLE = "answerable"
    UNANSWERABLE = "unanswerable"
    PARAPHRASE = "paraphrase"
    SKILL_VERIFICATION = "skill-verification"
    TECHNOLOGY = "technology"
    DEPLOYMENT = "deployment"
    METRIC = "metric"
    DATE = "date"
    OUTCOME = "outcome"
    EMPLOYMENT = "employment"
    EDUCATION = "education"
    AVAILABILITY = "availability"
    WEAK_MATCH = "weak-match"
    MULTI_PART = "multi-part"
    ADVERSARIAL = "adversarial"
    PRIVACY = "privacy"
    ACCESSIBILITY = "accessibility"


class RelevantPassage(DomainModel):
    source_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=2_000)

    @field_validator("source_id")
    @classmethod
    def source_id_is_stable(cls, value: str) -> str:
        if SOURCE_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("source ID must be a lowercase kebab-case slug")
        return value

    @field_validator("text")
    @classmethod
    def text_is_normalized(cls, value: str) -> str:
        normalized = normalize_evaluation_text(value)
        if not normalized:
            raise ValueError("relevant passage must not be blank")
        return normalized


class EvaluationCase(DomainModel):
    case_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=3, max_length=500)
    expected_status: EvaluationStatus
    reference_answer: str | None = Field(default=None, min_length=1, max_length=2_000)
    relevant_passages: tuple[RelevantPassage, ...] = Field(max_length=10)
    required_citation_source_ids: tuple[str, ...] = Field(max_length=10)
    tags: tuple[EvaluationTag, ...] = Field(min_length=1, max_length=10)

    @field_validator("case_id")
    @classmethod
    def case_id_is_stable(cls, value: str) -> str:
        if IDENTIFIER_PATTERN.fullmatch(value) is None:
            raise ValueError("case ID must be a lowercase kebab-case slug")
        return value

    @field_validator("question")
    @classmethod
    def question_is_normalized(cls, value: str) -> str:
        normalized = normalize_evaluation_text(value)
        if len(normalized) < 3:
            raise ValueError("question must contain at least 3 characters")
        return normalized

    @field_validator("reference_answer")
    @classmethod
    def reference_answer_is_normalized(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_evaluation_text(value)
        if not normalized:
            raise ValueError("reference answer must not be blank")
        return normalized

    @field_validator("required_citation_source_ids")
    @classmethod
    def citation_source_ids_are_stable(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("required citation source IDs must be unique")
        if any(SOURCE_ID_PATTERN.fullmatch(source_id) is None for source_id in value):
            raise ValueError(
                "required citation source IDs must be lowercase kebab-case slugs"
            )
        return value

    @field_validator("tags")
    @classmethod
    def tags_are_unique(
        cls, value: tuple[EvaluationTag, ...]
    ) -> tuple[EvaluationTag, ...]:
        if len(set(value)) != len(value):
            raise ValueError("evaluation tags must be unique")
        return value

    @model_validator(mode="after")
    def labels_match_expected_status(self) -> EvaluationCase:
        passage_keys = {
            (passage.source_id, passage.text) for passage in self.relevant_passages
        }
        if len(passage_keys) != len(self.relevant_passages):
            raise ValueError("relevant passages must be unique")

        tags = set(self.tags)
        if self.expected_status is EvaluationStatus.ANSWERED:
            if self.reference_answer is None:
                raise ValueError("answered case requires a reference answer")
            if not self.relevant_passages:
                raise ValueError("answered case requires relevant passages")
            if not self.required_citation_source_ids:
                raise ValueError("answered case requires citation sources")
            passage_source_ids = {
                passage.source_id for passage in self.relevant_passages
            }
            if not set(self.required_citation_source_ids).issubset(passage_source_ids):
                raise ValueError(
                    "required citation sources must have a relevant passage"
                )
            if (
                EvaluationTag.ANSWERABLE not in tags
                or EvaluationTag.UNANSWERABLE in tags
            ):
                raise ValueError("answered case requires only the answerable tag")
        else:
            if self.reference_answer is not None:
                raise ValueError("knowledge-gap case forbids a reference answer")
            if self.relevant_passages:
                raise ValueError("knowledge-gap case forbids relevant passages")
            if self.required_citation_source_ids:
                raise ValueError("knowledge-gap case forbids citation sources")
            if (
                EvaluationTag.UNANSWERABLE not in tags
                or EvaluationTag.ANSWERABLE in tags
            ):
                raise ValueError(
                    "knowledge-gap case requires only the unanswerable tag"
                )
        return self


class EvaluationSuite(DomainModel):
    schema_version: int = Field(ge=1, le=1)
    suite_id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    policy_version: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    cases: tuple[EvaluationCase, ...] = Field(min_length=1, max_length=500)

    @field_validator("suite_id")
    @classmethod
    def suite_id_is_stable(cls, value: str) -> str:
        if IDENTIFIER_PATTERN.fullmatch(value) is None:
            raise ValueError("suite ID must be a lowercase kebab-case slug")
        return value

    @field_validator("description")
    @classmethod
    def description_is_normalized(cls, value: str) -> str:
        normalized = normalize_evaluation_text(value)
        if not normalized:
            raise ValueError("description must not be blank")
        return normalized

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> EvaluationSuite:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case IDs must be unique")
        return self
