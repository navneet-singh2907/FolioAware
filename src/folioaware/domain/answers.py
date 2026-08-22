"""Question, evidence, generation, citation, and answer contracts."""

from enum import StrEnum

from pydantic import Field, field_validator

from folioaware.domain.base import DomainModel
from folioaware.domain.knowledge import validate_citation_url


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    PARTIAL = "partial"
    KNOWLEDGE_GAP = "knowledge_gap"


class Citation(DomainModel):
    source_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def citation_url_is_safe(cls, value: str) -> str:
        return validate_citation_url(value)


class Evidence(DomainModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=20_000)
    citation_title: str = Field(min_length=1, max_length=120)
    citation_url: str = Field(min_length=1, max_length=2048)
    index_version: str = Field(min_length=1, max_length=100)
    distance: float = Field(ge=0)

    @field_validator("citation_url")
    @classmethod
    def citation_url_is_safe(cls, value: str) -> str:
        return validate_citation_url(value)


class GenerationEvidence(DomainModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)


class GenerationRequest(DomainModel):
    question: str = Field(min_length=3, max_length=500)
    knowledge_version: str = Field(min_length=1, max_length=100)
    evidence: tuple[GenerationEvidence, ...] = Field(min_length=1, max_length=5)


class AnswerCandidate(DomainModel):
    answer: str = Field(min_length=1, max_length=2000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=5)


class AskResult(DomainModel):
    request_id: str = Field(min_length=1, max_length=100)
    answer: str = Field(min_length=1, max_length=2000)
    answer_status: AnswerStatus
    citations: tuple[Citation, ...]
    knowledge_version: str = Field(min_length=1, max_length=100)
