from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from typing import cast

from fastapi.testclient import TestClient

from folioaware.api.dependencies import build_local_container
from folioaware.api.main import create_app
from folioaware.application.answer_question import AnswerQuestion
from folioaware.config import Settings
from folioaware.domain.answers import AskResult

ALLOWED_ORIGIN = "https://portfolio.example"


def _settings(
    *,
    allowed_origins: tuple[str, ...] = (),
    per_client_requests: int = 2,
    global_requests: int = 10,
    answer_concurrency: int = 2,
) -> Settings:
    return Settings(
        allowed_origins=allowed_origins,
        rate_limit_per_client_requests=per_client_requests,
        rate_limit_global_requests=global_requests,
        rate_limit_window_seconds=60,
        rate_limit_max_clients=100,
        answer_concurrency_limit=answer_concurrency,
    )


def _client(settings: Settings) -> TestClient:
    return TestClient(
        create_app(build_local_container(settings), settings=settings),
        client=("203.0.113.10", 50000),
    )


class BlockingAnswerQuestion:
    def __init__(self, delegate: AnswerQuestion) -> None:
        self._delegate = delegate
        self.started = Event()
        self.release_request = Event()

    def execute(self, *, question: str, session_id: str | None) -> AskResult:
        self.started.set()
        if not self.release_request.wait(timeout=5):
            raise TimeoutError("test did not release blocked answer request")
        return self._delegate.execute(question=question, session_id=session_id)


def test_public_answer_limit_returns_stable_problem_and_retry_after() -> None:
    settings = _settings(allowed_origins=(ALLOWED_ORIGIN,))
    client = _client(settings)

    for _ in range(2):
        response = client.post(
            "/v1/ask",
            headers={"Origin": ALLOWED_ORIGIN},
            json={"question": "Have they used Kafka?"},
        )
        assert response.status_code == 200

    rejected = client.post(
        "/v1/ask",
        headers={"Origin": ALLOWED_ORIGIN},
        json={"question": "Have they used Kafka?"},
    )

    assert rejected.status_code == 429
    assert rejected.headers["retry-after"] == "60"
    assert rejected.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert rejected.headers["content-type"].startswith("application/problem+json")
    assert rejected.json()["code"] == "RATE_LIMITED"
    assert rejected.json()["requestId"]


def test_forwarding_headers_cannot_create_spoofed_client_buckets() -> None:
    settings = _settings(
        per_client_requests=1,
        global_requests=10,
    )
    client = _client(settings)

    first = client.post(
        "/v1/ask",
        headers={"X-Forwarded-For": "198.51.100.1"},
        json={"question": "Have they used Kafka?"},
    )
    second = client.post(
        "/v1/ask",
        headers={"X-Forwarded-For": "198.51.100.2"},
        json={"question": "Have they used Kafka?"},
    )

    assert first.status_code == 200
    assert second.status_code == 429


def test_health_owner_and_preflight_requests_do_not_consume_answer_quota() -> None:
    settings = _settings(
        allowed_origins=(ALLOWED_ORIGIN,),
        per_client_requests=1,
        global_requests=1,
    )
    client = _client(settings)

    for _ in range(3):
        assert client.get("/healthz").status_code == 200
        assert (
            client.options(
                "/v1/ask",
                headers={
                    "Origin": ALLOWED_ORIGIN,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/v1/owner/insights/report",
                json={
                    "periodStart": "2026-01-01T00:00:00Z",
                    "periodEnd": "2026-01-02T00:00:00Z",
                },
            ).status_code
            == 401
        )

    assert (
        client.post("/v1/ask", json={"question": "Have they used Kafka?"}).status_code
        == 200
    )
    assert (
        client.post("/v1/ask", json={"question": "Have they used Kafka?"}).status_code
        == 429
    )


def test_answer_concurrency_limit_rejects_excess_work_and_recovers() -> None:
    settings = _settings(
        per_client_requests=10,
        global_requests=20,
        answer_concurrency=1,
    )
    container = build_local_container(settings)
    blocking = BlockingAnswerQuestion(container.answer_question)
    guarded_container = replace(
        container,
        answer_question=cast(AnswerQuestion, blocking),
    )
    client = TestClient(
        create_app(guarded_container, settings=settings),
        client=("203.0.113.10", 50000),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        first_response = executor.submit(
            client.post,
            "/v1/ask",
            json={"question": "Have they used Kafka?"},
        )
        assert blocking.started.wait(timeout=2)
        rejected = client.post(
            "/v1/ask",
            json={"question": "Have they used Kafka?"},
        )
        blocking.release_request.set()
        completed = first_response.result(timeout=5)

    assert rejected.status_code == 503
    assert rejected.headers["retry-after"] == "1"
    assert rejected.json()["code"] == "ANSWER_CAPACITY_EXCEEDED"
    assert completed.status_code == 200

    recovered = client.post(
        "/v1/ask",
        json={"question": "Have they used Kafka?"},
    )
    assert recovered.status_code == 200
