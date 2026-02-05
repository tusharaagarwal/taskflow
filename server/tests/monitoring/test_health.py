"""
Unit tests for health monitoring endpoints.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.monitoring.health import router, check_database, get_system_health


class TestHealthFunctions:
    """Tests for health check helper functions."""

    @pytest.mark.asyncio
    async def test_check_database_healthy(self):
        """Test database health check when healthy."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_engine.connect.return_value = mock_conn

        healthy, message = await check_database(mock_engine)

        assert healthy is True
        assert message == "Database is healthy"

    @pytest.mark.asyncio
    async def test_check_database_unhealthy(self):
        """Test database health check when unhealthy."""
        mock_engine = MagicMock()
        mock_engine.connect = MagicMock(side_effect=Exception("Connection failed"))

        healthy, message = await check_database(mock_engine)

        assert healthy is False
        assert "Connection failed" in message

    @patch("app.monitoring.health.psutil")
    @patch("app.monitoring.health.time")
    @patch("app.main.start_time", 0)
    def test_get_system_health_healthy(self, mock_time, mock_psutil):
        """Test system health when resources are normal."""
        mock_psutil.cpu_percent.return_value = 50
        mock_psutil.virtual_memory.return_value = MagicMock(percent=60)
        mock_psutil.disk_usage.return_value = MagicMock(percent=70)
        mock_time.time.return_value = 1000

        healthy, metrics = get_system_health()

        assert healthy is True
        assert "cpu_usage" in metrics
        assert "memory_usage" in metrics

    @patch("app.monitoring.health.psutil")
    @patch("app.monitoring.health.time")
    @patch("app.main.start_time", 0)
    def test_get_system_health_unhealthy(self, mock_time, mock_psutil):
        """Test system health when resources are critical."""
        mock_psutil.cpu_percent.return_value = 95  # Above threshold
        mock_psutil.virtual_memory.return_value = MagicMock(percent=60)
        mock_psutil.disk_usage.return_value = MagicMock(percent=70)
        mock_time.time.return_value = 1000

        healthy, metrics = get_system_health()

        assert healthy is False


class TestHealthRouter:
    """Tests for health router endpoints."""

    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.include_router(router, prefix="/health")
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    @patch("app.monitoring.health.check_database")
    @patch("app.monitoring.health.get_system_health")
    def test_basic_health_check_healthy(self, mock_sys, mock_db, client):
        """Test comprehensive health check when healthy."""
        async def mock_check_db(engine):
            return True, "Database is healthy"

        with patch("app.monitoring.health.check_database", side_effect=mock_check_db):
            with patch(
                "app.monitoring.health.get_system_health",
                return_value=(True, {"cpu_usage": "50%"}),
            ):
                response = client.get("/health/_health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    @patch("app.monitoring.health.check_database")
    @patch("app.monitoring.health.get_system_health")
    def test_basic_health_check_unhealthy(self, mock_sys, mock_db, client):
        """Test comprehensive health check when unhealthy."""
        async def mock_check_db(engine):
            return False, "Connection failed"

        with patch("app.monitoring.health.check_database", side_effect=mock_check_db):
            with patch(
                "app.monitoring.health.get_system_health",
                return_value=(True, {"cpu_usage": "50%"}),
            ):
                response = client.get("/health/_health")

        assert response.status_code == 200
        assert response.json()["status"] == "unhealthy"

    @patch("app.monitoring.health.check_database")
    def test_readiness_check_ready(self, mock_db, client):
        """Test readiness check when ready."""
        async def mock_check_db(engine):
            return True, "OK"

        with patch("app.monitoring.health.check_database", side_effect=mock_check_db):
            response = client.get("/health/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    @patch("app.monitoring.health.check_database")
    def test_readiness_check_not_ready(self, mock_db, client):
        """Test readiness check when not ready."""
        async def mock_check_db(engine):
            return False, "DB unavailable"

        with patch("app.monitoring.health.check_database", side_effect=mock_check_db):
            response = client.get("/health/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "not_ready"

    def test_liveness_check(self, client):
        """Test liveness check always returns alive."""
        response = client.get("/health/live")

        assert response.status_code == 200
        assert response.json()["status"] == "alive"
