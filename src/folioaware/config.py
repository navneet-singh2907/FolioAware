"""Validated runtime configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FOLIOAWARE_",
        extra="ignore",
    )

    environment: str = "development"
    backend: Literal["local", "google"] = "local"
    session_hash_secret: SecretStr = SecretStr("local-development-only")
    content_root: Path = Path("examples/synthetic-portfolio")
    retrieval_distance_threshold: float = Field(default=0.85, ge=0, le=2)
    retrieval_top_k: int = Field(default=5, ge=1, le=5)
    telemetry_retention_days: int = Field(default=90, ge=1, le=365)
    insight_rules_path: Path = Path("examples/synthetic-portfolio/insight-topics.yaml")
    insight_min_question_count: int = Field(default=2, ge=2, le=100)
    owner_report_token: SecretStr = SecretStr("local-owner-report-token")
    google_cloud_project: str | None = Field(default=None, min_length=1)
    google_cloud_location: str = Field(default="global", min_length=1)
    firestore_database: str = Field(default="(default)", min_length=1)
    embedding_model: str = Field(default="gemini-embedding-001", min_length=1)
    embedding_dimensions: int = Field(default=768, ge=1, le=2048)
    generation_model: str | None = None
    google_request_timeout_seconds: int = Field(default=15, ge=1, le=60)
    generation_max_output_tokens: int = Field(default=512, ge=64, le=2048)

    @model_validator(mode="after")
    def production_requires_real_secret(self) -> Settings:
        secret = self.session_hash_secret.get_secret_value()
        if self.environment == "production" and (
            secret == "local-development-only" or len(secret) < 32
        ):
            raise ValueError(
                "production session hash secret must be at least 32 characters"
            )
        report_token = self.owner_report_token.get_secret_value()
        if self.environment == "production" and (
            report_token == "local-owner-report-token" or len(report_token) < 32
        ):
            raise ValueError(
                "production owner report token must be at least 32 characters"
            )
        if self.backend == "google" and (
            not self.google_cloud_project or not self.generation_model
        ):
            raise ValueError(
                "Google backend requires google_cloud_project and generation_model"
            )
        return self


class SyncSettings(BaseSettings):
    """Configuration required only by the knowledge synchronization process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FOLIOAWARE_",
        extra="ignore",
    )

    backend: Literal["local", "google"] = "local"
    google_cloud_project: str | None = Field(default=None, min_length=1)
    google_cloud_location: str = Field(default="global", min_length=1)
    firestore_database: str = Field(default="(default)", min_length=1)
    embedding_model: str = Field(default="gemini-embedding-001", min_length=1)
    embedding_dimensions: int = Field(default=768, ge=1, le=2048)
    google_request_timeout_seconds: int = Field(default=15, ge=1, le=60)

    @model_validator(mode="after")
    def google_sync_requires_project(self) -> SyncSettings:
        if self.backend == "google" and not self.google_cloud_project:
            raise ValueError("Google sync requires google_cloud_project")
        return self
