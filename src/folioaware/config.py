"""Validated runtime configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FOLIOAWARE_",
        extra="ignore",
    )

    environment: str = "development"
    session_hash_secret: SecretStr = SecretStr("local-development-only")
    content_root: Path = Path("examples/synthetic-portfolio")
    retrieval_distance_threshold: float = Field(default=0.85, ge=0, le=2)
    retrieval_top_k: int = Field(default=5, ge=1, le=5)
    telemetry_retention_days: int = Field(default=90, ge=1, le=365)

    @model_validator(mode="after")
    def production_requires_real_secret(self) -> Settings:
        secret = self.session_hash_secret.get_secret_value()
        if self.environment == "production" and (
            secret == "local-development-only" or len(secret) < 32
        ):
            raise ValueError(
                "production session hash secret must be at least 32 characters"
            )
        return self
