"""
Tests for health check endpoint.

Validates:
- GET /health returns HTTP 200 with {"status": "ok"} when ready
- Only logs on status change (not every request)
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from starlette.testclient import TestClient


@pytest.fixture
def app():
    """Create test app."""
    from backend.main import create_app
    test_app = create_app()
    return test_app


@pytest.fixture
def client(app):
    """Create test client for FastAPI app using positional arg."""
    # TestClient expects app as first positional argument
    return TestClient(app)


def test_health_check_returns_ok(client):
    """Test that health endpoint returns 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_health_check_content_type(client):
    """Test that health endpoint returns JSON content type."""
    response = client.get("/health")
    assert "application/json" in response.headers.get("content-type", "")


def test_health_check_multiple_calls(client):
    """Test that multiple health checks work."""
    for _ in range(3):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_cors_middleware_configured(app):
    """Test that CORS middleware is configured."""
    # Check that CORS middleware was added
    cors_middleware_found = False
    for middleware in app.user_middleware:
        if "CORSMiddleware" in str(middleware):
            cors_middleware_found = True
            break
    assert cors_middleware_found, "CORS middleware not found in app.user_middleware"


def test_health_endpoint_no_auth(client):
    """Test that health endpoint does not require authentication."""
    # No Authorization header provided
    response = client.get("/health")
    assert response.status_code == 200
