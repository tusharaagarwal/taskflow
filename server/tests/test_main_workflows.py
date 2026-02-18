"""
Unit tests for main.py workflow CRUD endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app, workflows_db, workflow_counter


class TestRootEndpoint:
    """Test root ping endpoint."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_ping_returns_pong(self, client):
        """GET / returns Pong."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == "Pong"


class TestWorkflowEndpoints:
    """Tests for workflow CRUD endpoints."""

    @pytest.fixture(autouse=True)
    def reset_db(self):
        """Reset in-memory database before each test."""
        workflows_db.clear()
        import app.main as main_module
        main_module.workflow_counter = 1
        yield
        workflows_db.clear()

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_workflows_empty(self, client):
        """Test getting workflows when empty."""
        response = client.get("/workflows")

        assert response.status_code == 200
        assert response.json() == []

    def test_create_workflow(self, client):
        """Test creating a new workflow."""
        response = client.post(
            "/workflows",
            json={"name": "Test Workflow", "description": "Test description"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Workflow"
        assert data["description"] == "Test description"
        assert data["status"] == "pending"

    def test_get_workflow_by_id(self, client):
        """Test getting a specific workflow."""
        client.post("/workflows", json={"name": "Test"})

        response = client.get("/workflows/1")

        assert response.status_code == 200
        assert response.json()["name"] == "Test"

    def test_get_workflow_not_found(self, client):
        """Test getting non-existent workflow."""
        response = client.get("/workflows/999")

        assert response.status_code == 404

    def test_update_workflow(self, client):
        """Test updating a workflow."""
        client.post("/workflows", json={"name": "Original"})

        response = client.put(
            "/workflows/1",
            json={"name": "Updated", "status": "active"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"
        assert data["status"] == "active"

    def test_update_workflow_not_found(self, client):
        """Test updating non-existent workflow."""
        response = client.put("/workflows/999", json={"name": "Test"})

        assert response.status_code == 404

    def test_delete_workflow(self, client):
        """Test deleting a workflow."""
        client.post("/workflows", json={"name": "To Delete"})

        response = client.delete("/workflows/1")

        assert response.status_code == 200
        assert "deleted" in response.json()["message"]

        # Verify it's gone
        assert client.get("/workflows/1").status_code == 404

    def test_delete_workflow_not_found(self, client):
        """Test deleting non-existent workflow."""
        response = client.delete("/workflows/999")

        assert response.status_code == 404
