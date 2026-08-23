"""Approved-source, chunk, embedding, and synchronization contracts."""

from __future__ import annotations

import math
import re
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from folioaware.domain.base import DomainModel

SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SourceType(StrEnum):
    PROJECT = "project"
    EXPERIENCE = "experience"
    SKILL = "skill"
    EDUCATION = "education"
    PROFILE = "profile"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"


class EmbeddingTaskType(StrEnum):
    RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
    RETRIEVAL_QUERY = "RETRIEVAL_QUERY"


class IndexStatus(StrEnum):
    BUILDING = "building"
    VALIDATING = "validating"
    ACTIVE = "active"
    FAILED = "failed"
    RETIRED = "retired"


class SyncStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def validate_citation_url(value: str) -> str:
    """Allow only safe HTTPS URLs and safe root-relative paths."""
    if any(ord(character) < 32 for character in value):
        raise ValueError("citation URL contains a control character")
    if value.startswith("/") and not value.startswith("//"):
        if "\\" in value:
            raise ValueError("root-relative citation URL contains a backslash")
        return value

    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("citation URL must be HTTPS or root-relative")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("citation URL must not contain user information")
    return value


class ApprovedSource(DomainModel):
    schema_version: int = Field(ge=1, le=1)
    source_id: str = Field(min_length=1, max_length=100)
    source_type: SourceType
    title: str = Field(min_length=1, max_length=120)
    citation_url: str = Field(min_length=1, max_length=2048)
    content: str = Field(min_length=1, max_length=20_000)
    tags: tuple[str, ...] = ()
    visibility: Visibility = Visibility.PUBLIC

    @field_validator("source_id")
    @classmethod
    def source_id_is_stable_slug(cls, value: str) -> str:
        if SOURCE_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("source ID must be a lowercase kebab-case slug")
        return value

    @field_validator("title", "content")
    @classmethod
    def text_is_not_only_whitespace(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped

    @field_validator("citation_url")
    @classmethod
    def citation_url_is_safe(cls, value: str) -> str:
        return validate_citation_url(value)

    @field_validator("tags")
    @classmethod
    def tags_are_normalized_and_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > 20:
            raise ValueError("at most 20 tags are allowed")
        if len(set(value)) != len(value):
            raise ValueError("tags must be unique")
        if any(TAG_PATTERN.fullmatch(tag) is None for tag in value):
            raise ValueError("tags must be lowercase kebab-case slugs")
        return value


class Embedding(DomainModel):
    values: tuple[float, ...]
    model: str = Field(min_length=1, max_length=200)
    task_type: EmbeddingTaskType
    dimensions: int = Field(ge=1, le=2048)

    @model_validator(mode="after")
    def vector_matches_contract(self) -> Embedding:
        if len(self.values) != self.dimensions:
            raise ValueError("embedding vector length must match dimensions")
        if any(not math.isfinite(value) for value in self.values):
            raise ValueError("embedding values must be finite")
        return self


class KnowledgeChunk(DomainModel):
    chunk_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=20_000)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    citation_title: str = Field(min_length=1, max_length=120)
    citation_url: str = Field(min_length=1, max_length=2048)
    evidence_status: EvidenceStatus = EvidenceStatus.VERIFIED
    visibility: Visibility = Visibility.PUBLIC
    embedding: Embedding
    index_version: str = Field(min_length=1, max_length=100)
    active: bool = True

    @field_validator("citation_url")
    @classmethod
    def citation_url_is_safe(cls, value: str) -> str:
        return validate_citation_url(value)


class IndexVersion(DomainModel):
    index_version: str = Field(min_length=1, max_length=100)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    status: IndexStatus
    source_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    embedding_model: str = Field(min_length=1, max_length=200)
    embedding_dimensions: int = Field(ge=1, le=2048)
    created_at: datetime
    activated_at: datetime | None = None


class SyncResult(DomainModel):
    sync_run_id: str = Field(min_length=1, max_length=100)
    candidate_index_version: str = Field(min_length=1, max_length=100)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    status: SyncStatus
    sources_seen: int = Field(ge=0)
    chunks_added: int = Field(ge=0)
    chunks_reused: int = Field(ge=0)
    chunks_removed: int = Field(ge=0)
    started_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def lifecycle_fields_match_status(self) -> SyncResult:
        if self.status is SyncStatus.RUNNING:
            if self.completed_at is not None or self.error_code is not None:
                raise ValueError("running sync cannot be completed or have an error")
        elif self.completed_at is None:
            raise ValueError("terminal sync must have a completion time")
        elif self.status is SyncStatus.SUCCEEDED and self.error_code is not None:
            raise ValueError("successful sync cannot have an error code")
        elif self.status is SyncStatus.FAILED and self.error_code is None:
            raise ValueError("failed sync must have an error code")
        return self
