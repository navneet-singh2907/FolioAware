from fastapi.testclient import TestClient

from folioaware.api.dependencies import build_local_container
from folioaware.api.main import create_app
from folioaware.config import Settings

ALLOWED_ORIGIN = "https://portfolio.example"
UNKNOWN_ORIGIN = "https://unknown.example"


def _client() -> TestClient:
    settings = Settings(allowed_origins=(ALLOWED_ORIGIN,))
    return TestClient(create_app(build_local_container(settings), settings=settings))


def _preflight_headers(
    *, origin: str = ALLOWED_ORIGIN, method: str = "POST", headers: str = "content-type"
) -> dict[str, str]:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": headers,
    }


def test_allowed_origin_preflight_is_narrow_and_credential_free() -> None:
    response = _client().options(
        "/v1/ask",
        headers=_preflight_headers(),
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "Origin" in response.headers["vary"]
    assert response.headers["access-control-allow-methods"] == "POST"
    allowed_headers = response.headers["access-control-allow-headers"].casefold()
    assert "content-type" in allowed_headers
    assert "authorization" not in allowed_headers
    assert "access-control-allow-credentials" not in response.headers


def test_allowed_origin_receives_cors_header_on_answer() -> None:
    response = _client().post(
        "/v1/ask",
        headers={"Origin": ALLOWED_ORIGIN},
        json={"question": "Have they used Kafka?"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_unknown_and_null_origins_are_not_allowed() -> None:
    client = _client()

    for origin in (UNKNOWN_ORIGIN, "null"):
        response = client.options(
            "/v1/ask",
            headers=_preflight_headers(origin=origin),
        )
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


def test_unknown_origin_request_is_processed_without_cors_permission() -> None:
    response = _client().post(
        "/v1/ask",
        headers={"Origin": UNKNOWN_ORIGIN},
        json={"question": "Have they used Kafka?"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_owner_authorization_header_is_rejected_by_preflight() -> None:
    response = _client().options(
        "/v1/owner/insights/report",
        headers=_preflight_headers(headers="authorization,content-type"),
    )

    assert response.status_code == 400
    allowed_headers = response.headers["access-control-allow-headers"].casefold()
    assert "authorization" not in allowed_headers


def test_cross_origin_get_is_rejected_and_non_browser_health_is_unchanged() -> None:
    client = _client()

    preflight = client.options(
        "/healthz",
        headers=_preflight_headers(method="GET"),
    )
    health = client.get("/healthz")

    assert preflight.status_code == 400
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert "access-control-allow-origin" not in health.headers


def test_default_configuration_allows_no_cross_origin_browser() -> None:
    response = TestClient(create_app()).post(
        "/v1/ask",
        headers={"Origin": ALLOWED_ORIGIN},
        json={"question": "Have they used Kafka?"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
