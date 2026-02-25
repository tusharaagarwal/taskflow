"""Tests for Workflow API: list, detail, update (PATCH), soft delete (DELETE)."""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from app.db.database import Base, get_db
from app.main import app as main_app
from app.models.workflow import Workflow

# Ensure config base_path for tests
import config_loader

config_loader.config.base_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)

# Sample workflow JSON for seeding
SAMPLE_WORKFLOW_JSON = {
    "id": "workflow_001",
    "workflow_name": "Publication Workflow",
    "description": "Standard publication workflow",
    "steps": [
        {
            "step_id": "draft_001",
            "step_name": "Draft",
            "stage_name": "Authoring",
            "transitions": {"success_goto": "review", "fail_goto": "NA"},
        }
    ],
}
SAMPLE_WORKFLOW_STR = json.dumps(SAMPLE_WORKFLOW_JSON)

# Workflow with name only in JSON (no name column)
WORKFLOW_JSON_NAME_ONLY = {
    "id": "workflow_002",
    "workflow_name": "From JSON Name",
    "steps": [],
}
WORKFLOW_JSON_NAME_ONLY_STR = json.dumps(WORKFLOW_JSON_NAME_ONLY)

# Workflow with no name anywhere
WORKFLOW_JSON_NO_NAME = {"id": "workflow_003", "steps": []}
WORKFLOW_JSON_NO_NAME_STR = json.dumps(WORKFLOW_JSON_NO_NAME)

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    try:
        policy = asyncio.WindowsSelectorEventLoopPolicy()
    except AttributeError:
        policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    async with async_sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        class_=AsyncSession,
    )() as session:
        yield session
        await session.rollback()


async def _seed_workflows(db: AsyncSession) -> None:
    """Insert test workflows into the workflow table."""
    now = datetime.now(timezone.utc)
    workflows = [
        Workflow(
            workflow_id=1,
            workflow_json=SAMPLE_WORKFLOW_STR,
            name="Stored Name",
            is_active=True,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        ),
        Workflow(
            workflow_id=2,
            workflow_json=WORKFLOW_JSON_NAME_ONLY_STR,
            name=None,
            is_active=True,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        ),
        Workflow(
            workflow_id=3,
            workflow_json=WORKFLOW_JSON_NO_NAME_STR,
            name=None,
            is_active=False,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        ),
    ]
    for w in workflows:
        db.add(w)
    await db.commit()


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        try:
            yield db
        finally:
            pass

    main_app.dependency_overrides[get_db] = override_get_db
    with TestClient(main_app) as test_client:
        yield test_client
    main_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_with_workflows(db):
    await _seed_workflows(db)

    async def override_get_db():
        try:
            yield db
        finally:
            pass

    main_app.dependency_overrides[get_db] = override_get_db
    with TestClient(main_app) as test_client:
        yield test_client
    main_app.dependency_overrides.clear()


class TestWorkflowList:
    """Tests for GET /api/v1/workflows."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        response = client.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_data(self, client_with_workflows):
        response = client_with_workflows.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        ids = [i["workflow_id"] for i in data["items"]]
        assert 1 in ids and 2 in ids and 3 in ids

    @pytest.mark.asyncio
    async def test_list_filter_is_active_true(self, client_with_workflows):
        response = client_with_workflows.get("/api/v1/workflows?is_active=true")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(i["is_active"] is True for i in data["items"])

    @pytest.mark.asyncio
    async def test_list_filter_is_active_false(self, client_with_workflows):
        response = client_with_workflows.get("/api/v1/workflows?is_active=false")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["is_active"] is False
        assert data["items"][0]["workflow_id"] == 3

    @pytest.mark.asyncio
    async def test_list_name_resolution(self, client_with_workflows):
        """Name: column > workflow_json.workflow_name > null."""
        response = client_with_workflows.get("/api/v1/workflows")
        assert response.status_code == 200
        by_id = {i["workflow_id"]: i for i in response.json()["items"]}
        assert by_id[1]["name"] == "Stored Name"
        assert by_id[2]["name"] == "From JSON Name"
        assert by_id[3]["name"] is None


class TestWorkflowDetail:
    """Tests for GET /api/v1/workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_get_detail_200(self, client_with_workflows):
        response = client_with_workflows.get("/api/v1/workflows/1")
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == 1
        assert data["name"] == "Stored Name"
        assert data["is_active"] is True
        assert "workflow_json" in data
        assert data["workflow_json"].get("workflow_name") == "Publication Workflow"
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_detail_name_from_json(self, client_with_workflows):
        response = client_with_workflows.get("/api/v1/workflows/2")
        assert response.status_code == 200
        assert response.json()["name"] == "From JSON Name"

    @pytest.mark.asyncio
    async def test_get_detail_name_null(self, client_with_workflows):
        response = client_with_workflows.get("/api/v1/workflows/3")
        assert response.status_code == 200
        assert response.json()["name"] is None

    @pytest.mark.asyncio
    async def test_get_detail_404(self, client_with_workflows):
        response = client_with_workflows.get("/api/v1/workflows/999")
        assert response.status_code == 404
        assert "999" in response.json()["detail"]


class TestWorkflowUpdate:
    """Tests for PATCH /api/v1/workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_patch_partial_name(self, client_with_workflows):
        response = client_with_workflows.patch(
            "/api/v1/workflows/1",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["workflow_id"] == 1
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_patch_partial_is_active(self, client_with_workflows):
        response = client_with_workflows.patch(
            "/api/v1/workflows/1",
            json={"is_active": False},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_patch_workflow_json(self, client_with_workflows):
        new_json = {"id": "patched", "steps": []}
        response = client_with_workflows.patch(
            "/api/v1/workflows/2",
            json={"workflow_json": new_json},
        )
        assert response.status_code == 200
        assert response.json()["workflow_json"] == new_json

    @pytest.mark.asyncio
    async def test_patch_404(self, client_with_workflows):
        response = client_with_workflows.patch(
            "/api/v1/workflows/999",
            json={"name": "X"},
        )
        assert response.status_code == 404


class TestWorkflowSoftDelete:
    """Tests for DELETE /api/v1/workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_delete_204(self, client_with_workflows):
        response = client_with_workflows.delete("/api/v1/workflows/1")
        assert response.status_code == 204
        assert response.content in (b"", b" ")

    @pytest.mark.asyncio
    async def test_delete_then_list_excludes(self, client_with_workflows):
        client_with_workflows.delete("/api/v1/workflows/1")
        response = client_with_workflows.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        ids = [i["workflow_id"] for i in data["items"]]
        assert 1 not in ids

    @pytest.mark.asyncio
    async def test_delete_then_get_404(self, client_with_workflows):
        client_with_workflows.delete("/api/v1/workflows/2")
        response = client_with_workflows.get("/api/v1/workflows/2")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_404_not_found(self, client_with_workflows):
        response = client_with_workflows.delete("/api/v1/workflows/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_404_already_deleted(self, client_with_workflows):
        client_with_workflows.delete("/api/v1/workflows/1")
        response = client_with_workflows.delete("/api/v1/workflows/1")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_after_delete_404(self, client_with_workflows):
        client_with_workflows.delete("/api/v1/workflows/1")
        response = client_with_workflows.patch(
            "/api/v1/workflows/1",
            json={"name": "X"},
        )
        assert response.status_code == 404


class TestWorkflowServiceNameResolution:
    """Unit-style tests for resolve_workflow_name behavior via API."""

    @pytest.mark.asyncio
    async def test_name_from_column_takes_precedence(self, client_with_workflows):
        """Even when workflow_json has workflow_name, column name wins."""
        response = client_with_workflows.get("/api/v1/workflows/1")
        assert response.json()["name"] == "Stored Name"
