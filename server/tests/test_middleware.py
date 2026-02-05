"""
Unit tests for middleware components.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.middleware import RequestResponseMiddleware, SecurityHeadersMiddleware


class TestRequestResponseMiddleware:
    """Tests for RequestResponseMiddleware."""

    @pytest.fixture
    def app_with_middleware(self):
        app = FastAPI()
        app.add_middleware(RequestResponseMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        @app.get("/error")
        async def error_endpoint():
            raise HTTPException(status_code=404, detail="Not found")

        @app.get("/server-error")
        async def server_error_endpoint():
            raise Exception("Unexpected error")

        return app

    @pytest.fixture
    def client(self, app_with_middleware):
        return TestClient(app_with_middleware)

    def test_successful_request_adds_headers(self, client):
        """Test successful requests get proper headers."""
        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert "X-Correlation-ID" in response.headers
        assert "X-Process-Time" in response.headers
        assert "X-API-Version" in response.headers

    def test_correlation_id_forwarded(self, client):
        """Test that provided correlation ID is forwarded."""
        response = client.get(
            "/test",
            headers={"X-Correlation-ID": "test-correlation-123"},
        )

        assert response.headers["X-Correlation-ID"] == "test-correlation-123"

    def test_http_exception_handling(self, client):
        """Test HTTP exceptions are handled properly."""
        response = client.get("/error")

        assert response.status_code == 404
        assert "X-Request-ID" in response.headers
        assert response.json()["detail"] == "Not found"

    def test_unexpected_exception_handling(self, client):
        """Test unexpected exceptions return 500."""
        response = client.get("/server-error")

        assert response.status_code == 500
        assert "X-Request-ID" in response.headers


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    @pytest.fixture
    def app_with_security(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        return app

    @pytest.fixture
    def client(self, app_with_security):
        return TestClient(app_with_security)

    def test_security_headers_added(self, client):
        """Test security headers are added to response."""
        response = client.get("/test")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert (
            response.headers["Referrer-Policy"]
            == "strict-origin-when-cross-origin"
        )
        assert (
            response.headers["Cache-Control"]
            == "no-cache, no-store, must-revalidate"
        )
