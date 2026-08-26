import pytest
from pydantic import SecretStr, ValidationError

from folioaware.config import Settings, SyncSettings


def test_production_rejects_development_session_secret() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(environment="production")


def test_production_accepts_explicit_strong_session_secret() -> None:
    settings = Settings(
        environment="production",
        session_hash_secret=SecretStr("a-strong-production-secret-with-32-characters"),
        owner_report_token=SecretStr("a-strong-owner-report-token-with-32-characters"),
        allowed_origins=("https://portfolio.example/",),
    )

    assert settings.environment == "production"
    assert settings.allowed_origins == ("https://portfolio.example",)


def test_production_rejects_development_owner_report_token() -> None:
    with pytest.raises(ValidationError, match="owner report token"):
        Settings(
            environment="production",
            session_hash_secret=SecretStr(
                "a-strong-production-secret-with-32-characters"
            ),
        )


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


def test_google_sync_requires_only_project_and_embedding_configuration() -> None:
    settings = SyncSettings(
        backend="google",
        google_cloud_project="synthetic-project",
    )

    assert settings.embedding_model == "gemini-embedding-001"


def test_google_sync_rejects_missing_project() -> None:
    with pytest.raises(ValidationError, match="Google sync requires"):
        SyncSettings(backend="google")


def test_allowed_origins_are_normalized_and_deduplicated() -> None:
    settings = Settings(
        allowed_origins=(
            "HTTPS://Portfolio.Example:443/",
            "https://portfolio.example",
        )
    )

    assert settings.allowed_origins == ("https://portfolio.example",)


@pytest.mark.parametrize(
    "origin",
    (
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://[::1]:4173",
    ),
)
def test_development_allows_loopback_http_origin(origin: str) -> None:
    settings = Settings(allowed_origins=(origin,))

    assert settings.allowed_origins == (origin,)


def test_development_rejects_non_loopback_http_origin() -> None:
    with pytest.raises(ValidationError, match="local development"):
        Settings(allowed_origins=("http://portfolio.example",))


def test_production_rejects_loopback_http_origin() -> None:
    with pytest.raises(ValidationError, match="local development"):
        Settings(
            environment="production",
            session_hash_secret=SecretStr(
                "a-strong-production-secret-with-32-characters"
            ),
            owner_report_token=SecretStr(
                "a-strong-owner-report-token-with-32-characters"
            ),
            allowed_origins=("http://localhost:4173",),
        )


@pytest.mark.parametrize(
    "origin",
    (
        "*",
        "https://*.example.com",
        "ftp://portfolio.example",
        "https://user@portfolio.example",
        "https://portfolio.example/widget",
        "https://portfolio.example?mode=widget",
        "https://portfolio.example#widget",
        "https://portfolio.example:99999",
    ),
)
def test_allowed_origins_reject_non_origin_values(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(allowed_origins=(origin,))


def test_allowed_origins_load_from_json_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FOLIOAWARE_ALLOWED_ORIGINS",
        '["https://portfolio.example", "https://www.portfolio.example"]',
    )

    settings = Settings()

    assert settings.allowed_origins == (
        "https://portfolio.example",
        "https://www.portfolio.example",
    )
