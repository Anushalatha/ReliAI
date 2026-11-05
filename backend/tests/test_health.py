from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_request_id_is_propagated(client):
    response = client.get("/health", headers={"X-Request-ID": "test-request-123"})

    assert response.headers["x-request-id"] == "test-request-123"


def test_invalid_request_id_is_replaced(client):
    response = client.get("/health", headers={"X-Request-ID": "bad value"})

    assert response.headers["x-request-id"] != "bad value"


def test_frontend_cors_origin_is_allowed(client):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_readiness_checks_database(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_readiness_reports_database_failure(client):
    class UnavailableSession(Session):
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, OSError("database unavailable"))

    def override_get_db():
        with UnavailableSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Database unavailable"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
