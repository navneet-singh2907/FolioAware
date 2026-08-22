"""Privacy-reduced visitor telemetry contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from folioaware.domain.answers import AnswerStatus
from folioaware.domain.base import DomainModel


class QuestionIntent(StrEnum):
    SKILL_VERIFICATION = "skill_verification"
    PROJECT_EXPERIENCE = "project_experience"
    ARCHITECTURE = "architecture"
    AVAILABILITY = "availability"
    UNKNOWN = "unknown"


class VisitorQuestion(DomainModel):
    question_id: str = Field(min_length=1, max_length=100)
    redacted_question: str = Field(min_length=1, max_length=500)
    session_hash: str | None = Field(default=None, max_length=200)
    intent: QuestionIntent = QuestionIntent.UNKNOWN
    topics: tuple[str, ...] = ()
    answer_status: AnswerStatus
    knowledge_version: str = Field(min_length=1, max_length=100)
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def expiry_follows_creation(self) -> VisitorQuestion:
        if self.expires_at <= self.created_at:
            raise ValueError("telemetry expiry must follow creation")
        return self


class SuggestedAction(StrEnum):
    ADD_EXISTING_EVIDENCE = "add_existing_evidence"
    BUILD_PROJECT = "build_project"
    STUDY_TOPIC = "study_topic"
    LEAVE_UNAVAILABLE = "leave_unavailable"


class TopicRule(DomainModel):
    """Owner-configured aliases used only to classify sanitized telemetry."""

    topic: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    aliases: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, aliases: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(" ".join(alias.casefold().split()) for alias in aliases)
        if any(not alias or len(alias) > 80 for alias in normalized):
            raise ValueError("topic aliases must contain 1 to 80 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("topic aliases must be unique")
        return normalized


class ClassifiedQuestion(DomainModel):
    intent: QuestionIntent
    topics: tuple[str, ...]


class TopicInsight(DomainModel):
    insight_id: str = Field(min_length=1, max_length=200)
    topic: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    period_start: datetime
    period_end: datetime
    distinct_session_count: int = Field(ge=0)
    question_count: int = Field(ge=1)
    skill_verification_count: int = Field(ge=0)
    knowledge_gap_count: int = Field(ge=0)
    suggested_action: SuggestedAction
    created_at: datetime

    @model_validator(mode="after")
    def validate_counts_and_period(self) -> TopicInsight:
        if self.period_end <= self.period_start:
            raise ValueError("insight period end must follow its start")
        if self.skill_verification_count > self.question_count:
            raise ValueError("skill verification count exceeds question count")
        if self.knowledge_gap_count > self.question_count:
            raise ValueError("knowledge gap count exceeds question count")
        return self


class InsightReport(DomainModel):
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    minimum_question_count: int = Field(ge=2)
    analyzed_question_count: int = Field(ge=0)
    insights: tuple[TopicInsight, ...]

    @model_validator(mode="after")
    def period_is_valid(self) -> InsightReport:
        if self.period_end <= self.period_start:
            raise ValueError("report period end must follow its start")
        return self
