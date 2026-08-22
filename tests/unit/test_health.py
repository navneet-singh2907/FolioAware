from fastapi.testclient import TestClient

from folioaware.api.main import create_app


def test_health_endpoint_reports_ok() -> None:
    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
