"""Public HTTP models, separate from persistence and provider models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from folioaware.domain.answers import AnswerStatus, AskResult


class PublicModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class AskRequest(PublicModel):
    question: str = Field(min_length=3, max_length=500)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("question must contain at least 3 characters")
        return normalized


class CitationResponse(PublicModel):
    source_id: str
    title: str
    url: str


class AskResponse(PublicModel):
    request_id: str
    answer: str
    answer_status: AnswerStatus
    citations: tuple[CitationResponse, ...]
    knowledge_version: str

    @classmethod
    def from_result(cls, result: AskResult) -> AskResponse:
        return cls(
            request_id=result.request_id,
            answer=result.answer,
            answer_status=result.answer_status,
            citations=tuple(
                CitationResponse(
                    source_id=citation.source_id,
                    title=citation.title,
                    url=citation.url,
                )
                for citation in result.citations
            ),
            knowledge_version=result.knowledge_version,
        )


class ProblemResponse(PublicModel):
    type: str
    title: str
    status: int
    code: str
    request_id: str
