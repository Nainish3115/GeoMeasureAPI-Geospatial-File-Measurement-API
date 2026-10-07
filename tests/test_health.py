"""Tests for the health check endpoint and application initialization."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_app_initialization() -> None:
    """Verify FastAPI application instance is properly configured."""
    assert app.title == "Geospatial File Measurement API"
    assert app.version == "0.1.0"


def test_health_check_status_code() -> None:
    """Verify GET /health returns HTTP 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_payload() -> None:
    """Verify GET /health response payload matches the expected schema."""
    response = client.get("/health")
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert data == {"status": "healthy"}
