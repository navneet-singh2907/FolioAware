from datetime import UTC, datetime

from fastapi.testclient import TestClient

from folioaware.api.dependencies import build_local_container
from folioaware.api.main import create_app


def test_owner_report_requires_bearer_token_and_returns_repeated_topics() -> None:
    container = build_local_container()
    client = TestClient(create_app(container))
    for session in ("visitor-a", "visitor-b"):
        response = client.post(
            "/v1/ask",
            json={"question": "Have they used Kafka?", "sessionId": session},
        )
        assert response.status_code == 200

    payload = {
        "periodStart": datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        "periodEnd": datetime(2030, 1, 1, tzinfo=UTC).isoformat(),
    }
    unauthorized = client.post("/v1/owner/insights/report", json=payload)
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"
    assert unauthorized.json()["code"] == "OWNER_AUTHENTICATION_REQUIRED"

    response = client.post(
        "/v1/owner/insights/report",
        json=payload,
        headers={
            "Authorization": (
                f"Bearer {container.owner_report_token.get_secret_value()}"
            )
        },
    )

    assert response.status_code == 422  # Periods are deliberately bounded.


def test_owner_report_returns_camel_case_contract_for_bounded_period() -> None:
    container = build_local_container()
    client = TestClient(create_app(container))
    client.post("/v1/ask", json={"question": "Have they used Kafka?"})
    client.post("/v1/ask", json={"question": "Did they work with Kafka?"})
    now = container.clock.now()

    response = client.post(
        "/v1/owner/insights/report",
        json={
            "periodStart": datetime(now.year, now.month, 1, tzinfo=UTC).isoformat(),
            "periodEnd": now.isoformat(),
        },
        headers={
            "Authorization": (
                f"Bearer {container.owner_report_token.get_secret_value()}"
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analyzedQuestionCount"] == 2
    assert body["insights"][0]["topic"] == "apache-kafka"
    assert body["insights"][0]["knowledgeGapCount"] == 2
    assert body["insights"][0]["suggestedAction"] == "build_project"
