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
