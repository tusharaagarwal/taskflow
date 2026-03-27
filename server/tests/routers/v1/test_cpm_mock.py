"""
Unit tests for CPM mock router endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.routers.v1.cpm_mock import (
    router,
    generate_deterministic_uuid,
    get_cpm_mock_data,
)

# Create test app
app = FastAPI()
app.include_router(router, prefix="/v1")


class TestCPMMockHelpers:
    """Tests for CPM mock helper functions."""

    def test_generate_deterministic_uuid(self):
        """Test UUID generation is deterministic."""
        uuid1 = generate_deterministic_uuid("test-seed")
        uuid2 = generate_deterministic_uuid("test-seed")
        uuid3 = generate_deterministic_uuid("different-seed")

        assert uuid1 == uuid2  # Same seed = same UUID
        assert uuid1 != uuid3  # Different seed = different UUID

    def test_get_cpm_mock_data_structure(self):
        """Test mock data has correct structure."""
        data = get_cpm_mock_data("banking", "figbanking", "Credit Opinion")

        assert "cp_id" in data
        assert "cp_name" in data
        assert "lob" in data
        assert "sub_lob" in data
        assert "workflow_id" in data
        assert data["workflow_id"] is None  # workflow_id is resolved by caller via get_config_value
        assert "content_blocks" in data
        assert len(data["content_blocks"]) == 2

    def test_get_cpm_mock_data_content_blocks(self):
        """Test content blocks have correct structure."""
        data = get_cpm_mock_data("banking", "figbanking", "Credit Opinion")

        block = data["content_blocks"][0]
        assert "block_id" in block
        assert "block_name" in block
        assert "primitives_allowed" in block


class TestCPMMockRouter:
    """Tests for CPM mock router endpoints."""

    @pytest.fixture
    def client(self):
        with TestClient(app) as test_client:
            yield test_client

    def test_search_cpm(self, client):
        """Test CPM search endpoint returns mock data with workflow_id=None."""
        response = client.get(
            "/v1/cpm/search",
            params={
                "lob": "banking",
                "sub_lob": "figbanking",
                "cp_name": "Credit Opinion",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["lob"] == "banking"
        assert data["sub_lob"] == "figbanking"
        assert data["cp_name"] == "Credit Opinion"
        assert data["workflow_id"] is None  # resolved by caller

    def test_get_cpm_detail(self, client):
        """Test CPM detail endpoint returns mock data with workflow_id=None."""
        response = client.get("/v1/cpm/test-cp-id-123")

        assert response.status_code == 200
        data = response.json()
        assert data["cp_id"] == "test-cp-id-123"
        assert data["workflow_id"] is None  # resolved by caller

    def test_search_cpm_missing_params(self, client):
        """Test search with missing parameters returns validation error."""
        response = client.get("/v1/cpm/search")

        assert response.status_code == 422  # Validation error
