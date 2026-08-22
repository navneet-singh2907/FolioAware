"""Privacy-reduced visitor telemetry contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

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
