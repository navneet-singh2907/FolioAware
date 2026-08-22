import pytest
from pydantic import SecretStr, ValidationError

from folioaware.config import Settings


def test_production_rejects_development_session_secret() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(environment="production")


def test_production_accepts_explicit_strong_session_secret() -> None:
    settings = Settings(
        environment="production",
        session_hash_secret=SecretStr("a-strong-production-secret-with-32-characters"),
    )

    assert settings.environment == "production"


def test_google_backend_requires_project_and_generation_model() -> None:
    with pytest.raises(ValidationError, match="Google backend requires"):
        Settings(backend="google")


def test_google_backend_accepts_explicit_model_configuration() -> None:
    settings = Settings(
        backend="google",
        google_cloud_project="synthetic-project",
        generation_model="generation-model",
    )

    assert settings.embedding_dimensions == 768
