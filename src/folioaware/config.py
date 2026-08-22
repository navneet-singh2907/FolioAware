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
    google_cloud_project: str | None = None
    google_cloud_location: str = "global"
    firestore_database: str = "(default)"
    embedding_model: str = "gemini-embedding-001"
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
        if self.backend == "google" and (
            not self.google_cloud_project or not self.generation_model
        ):
            raise ValueError(
                "Google backend requires google_cloud_project and generation_model"
            )
        return self
