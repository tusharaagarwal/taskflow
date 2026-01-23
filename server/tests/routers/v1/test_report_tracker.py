import pytest
import asyncio
import pytest_asyncio
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text
from datetime import datetime, timezone
import os
import sys

# Import WorkflowActionType for testing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from app.constants import WorkflowActionType

# Add the server directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

# Import after setting up the path
from fastapi import FastAPI
from unittest.mock import AsyncMock, patch
from app.main import app as main_app
from app.db.database import Base, get_db
from app.models.content_product import ContentProduct
from app.models.report_tracker import ReportTracker
from app.routers.v1.report_tracker import router as report_tracker_router
from app.schemas.report_tracker import ReportTrackerCreateRequest
from app.services.cpm_client_service import CPMClientService
from app.services.workflow_service import WorkflowService
from config_loader import config
import json

# Default CPM filters used in test payloads
DEFAULT_LOB = "banking"
DEFAULT_SUB_LOB = "figbanking"

# Sample workflow data for testing
SAMPLE_WORKFLOW = {
    "steps": [
        {
            "step_id": "draft",
            "step_name": "Initial Draft",
            "stage_name": "Authoring",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": [],
            "personas": [],
            "transitions": {
                "success_goto": "review",
                "fail_goto": "NA"
            }
        },
        {
            "step_id": "review",
            "step_name": "Review",
            "stage_name": "Review",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": [],
            "personas": [],
            "transitions": {
                "success_goto": "approval",
                "fail_goto": "draft"
            }
        },
        {
            "step_id": "approval",
            "step_name": "Approval",
            "stage_name": "Approval",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": [],
            "personas": [],
            "transitions": {
                "success_goto": "publish",
                "fail_goto": "review"
            }
        },
        {
            "step_id": "publish",
            "step_name": "Publish",
            "stage_name": "Published",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": [],
            "personas": [],
            "transitions": {
                "success_goto": "NA",
                "fail_goto": "NA"
            }
        }
    ]
}

SAMPLE_WORKFLOW_JSON = json.dumps(SAMPLE_WORKFLOW)

# Mock for ContentProduct.get_workflow_json
async def mock_get_workflow_json(self, db):
    # Return a sample workflow based on the workflow_id
    workflow_map = {
        1: SAMPLE_WORKFLOW,
        2: SAMPLE_WORKFLOW,
        3: SAMPLE_WORKFLOW
    }
    return workflow_map.get(self.workflow_id)

# Apply the mock to ContentProduct.get_workflow_json
ContentProduct.get_workflow_json = mock_get_workflow_json

# Sample content products for testing
SAMPLE_CONTENT_PRODUCTS = [
    {
        "id": 1,
        "name": "Credit Opinion",
        "workflow_id": 1
    },
    {
        "id": 2,
        "name": "Research Report",
        "workflow_id": 2
    },
    {
        "id": 3,
        "name": "Market Analysis",
        "workflow_id": 3
    }
]

# Create a test app with only the report tracker router
test_app = FastAPI()
test_app.include_router(report_tracker_router)

# Apply the mock to ContentProduct.get_workflow_json
ContentProduct.get_workflow_json = mock_get_workflow_json

# Update the base path for the config
config.base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# Mock CPM + workflow service calls for create flow
@pytest.fixture(autouse=True)
def mock_cpm_and_workflow(monkeypatch):
    async def mock_get_cpm_by_filters(lob: str, sub_lob: str, cp_name: str):
        return {"workflow_id": 1}

    async def mock_get_workflow_json_from_workflow(db, workflow_id: int):
        return SAMPLE_WORKFLOW

    monkeypatch.setattr(CPMClientService, "get_cpm_by_filters", mock_get_cpm_by_filters)
    monkeypatch.setattr(WorkflowService, "get_workflow_json_from_workflow", mock_get_workflow_json_from_workflow)

# This event_loop fixture is required for async tests
@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.WindowsSelectorEventLoopPolicy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as conn:
        # Drop all tables first to ensure a clean state
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db(engine):
    async with async_sessionmaker(
        autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
    )() as session:
        yield session
        await session.rollback()

# Helper function to create test content products
async def _create_test_workflow_table(db):
    """Create the workflow table and add test data."""
    # No need to create the workflow table since we're mocking the get_workflow_json method
    pass

async def _create_test_content_products(db):
    """Create content products table and add test data."""
    # First create the workflow table
    await _create_test_workflow_table(db)
    
    # Create content_products table if it doesn't exist
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='content_product'"))
    if not result.scalar():
        await db.execute(text("""
            CREATE TABLE content_product (
                id INTEGER NOT NULL, 
                name VARCHAR, 
                workflow_id INTEGER, 
                PRIMARY KEY (id)
            )
        """))
        await db.commit()
    
    # Clear existing data
    await db.execute(text("DELETE FROM content_product"))
    await db.commit()
    
    # Add test data
    for cp in SAMPLE_CONTENT_PRODUCTS:
        await db.execute(
            text("INSERT INTO content_product (id, name, workflow_id) VALUES (:id, :name, :workflow_id)"),
            {"id": cp["id"], "name": cp["name"], "workflow_id": cp["workflow_id"]}
        )
    await db.commit()
    
    # Return the created products
    result = await db.execute(text("SELECT * FROM content_product"))
    return [dict(row) for row in result.mappings()]

@pytest_asyncio.fixture(scope="function")
async def client(db):
    async def override_get_db():
        try:
            yield db
        finally:
            await db.close()
    
    test_app.dependency_overrides[get_db] = override_get_db
    
    # Create a new TestClient for each test
    with TestClient(test_app) as test_client:
        yield test_client
    
    test_app.dependency_overrides.clear()

@pytest_asyncio.fixture(scope="function")
async def sample_report_tracker(db):
    # First ensure we have content products
    await _create_test_content_products(db)
    
    # Ensure the report_tracker table exists
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='report_tracker'"))
    if not result.scalar():
        await db.execute(text("""
            CREATE TABLE report_tracker (
                id INTEGER NOT NULL, 
                report_id VARCHAR, 
                workflow_json TEXT, 
                workflow_steps_json TEXT, 
                created_at DATETIME, 
                updated_at DATETIME, 
                PRIMARY KEY (id), 
                UNIQUE (report_id)
            )
        
        """))
        await db.commit()
    
    # Clear existing data
    await db.execute(text("DELETE FROM report_tracker"))
    await db.commit()
    
    # Create a sample workflow steps JSON aligned with current workflow structure
    workflow_steps = ReportTrackerCreateRequest.create_workflow_steps_json(SAMPLE_WORKFLOW)
    
    # Create a report tracker
    tracker = ReportTracker(
        report_id="PR-12345",
        workflow_json=SAMPLE_WORKFLOW,
        workflow_steps_json=workflow_steps,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.add(tracker)
    await db.commit()
    await db.refresh(tracker)
    return tracker

# Tests
class TestReportTracker:
    @pytest.mark.asyncio
    async def test_create_report_tracker(self, client, db):
        # First ensure we have content products
        await _create_test_content_products(db)
        
        # Test data
        report_data = {
            "report_id": "PR-12345",
            "content_product_name": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB
        }
        
        # Make request
        response = client.post("/report-tracker/", json=report_data)
        
        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["report_id"] == report_data["report_id"]
        assert "workflow_steps_json" in data

    @pytest.mark.asyncio
    async def test_get_report_tracker(self, client, db):
        # First ensure we have content products
        await _create_test_content_products(db)
        
        # First create a report
        report_data = {
            "report_id": "PR-67890",
            "content_product_name": "Research Report",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB
        }
        create_response = client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        
        # Now get the report
        report_id = create_response.json()["report_id"]
        response = client.get(f"/report-tracker/{report_id}")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["report_id"] == report_id
        assert "workflow_json" in data
        assert "workflow_steps_json" in data

    @pytest.mark.asyncio
    async def test_update_report_status_flow(self, client, sample_report_tracker):
        # Test accept flow
        actions = ["accept", "accept", "reject", "accept", "accept"]

        for i, action in enumerate(actions, 1):
            update_data = {
                "action": action,
                "assignee": f"user{i}@example.com",
                "role": f"Role {i}",
                "start_date": "2025-11-01T09:00:00Z",
                "due_date": "2025-11-15T18:00:00Z"
            }

            # Use the sample_report_tracker directly (no need to await)
            response = client.put(
                f"/report-tracker/{sample_report_tracker.report_id}",
                json=update_data
            )

            # Assertions
            # All actions should return 200 OK, including reject
            assert response.status_code == 200, f"Failed on action {action}"
            data = response.json()
            assert "workflow_steps_json" in data
            assert "progress_tracker" in data["workflow_steps_json"]

    @pytest.mark.asyncio
    async def test_get_report_status(self, client, sample_report_tracker):
        # Get status
        response = client.get(f"/report-tracker/{sample_report_tracker.report_id}/status")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["report_id"] == sample_report_tracker.report_id
        assert "progress_tracker" in data

    @pytest.mark.asyncio
    async def test_list_report_trackers(self, client, db):
        # First ensure we have content products
        await _create_test_content_products(db)
        
        # Create a couple of reports
        reports = [
            {"report_id": "PR-11111", "content_product_name": "Credit Opinion", "lob": DEFAULT_LOB, "sub_lob": DEFAULT_SUB_LOB},
            {"report_id": "PR-22222", "content_product_name": "Market Analysis", "lob": DEFAULT_LOB, "sub_lob": DEFAULT_SUB_LOB}
        ]
        
        # Store created report IDs for later verification
        created_report_ids = []
        
        for report in reports:
            response = client.post("/report-tracker/", json=report)
            assert response.status_code == status.HTTP_201_CREATED
            created_report_ids.append(response.json()["report_id"])
        
        # List all reports
        response = client.get("/report-tracker/")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # At least the two we just created
        
        # Verify all created reports are in the list
        report_ids = [item["report_id"] for item in data]
        for report_id in created_report_ids:
            assert report_id in report_ids
            
        # Verify each item has the expected structure
        for item in data:
            assert "id" in item
            assert isinstance(item["id"], str)  # UUID is a string
            assert "report_id" in item
            assert isinstance(item["report_id"], str)
            
        # Test with empty database (after clearing)
        # Clear the database using SQLAlchemy's text() function
        from sqlalchemy import text
        await db.execute(text("DELETE FROM report_tracker"))
        await db.commit()
        
        # Verify the database is empty
        response = client.get("/report-tracker/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0  # Should be empty after clearing

    @pytest.mark.asyncio
    async def test_update_nonexistent_report_tracker(self, client, db):
        # Try to update a non-existent report
        update_data = {
            "action": "accept",
            "assignee": "user@example.com",
            "role": "Reviewer",
            "start_date": "2025-11-01T09:00:00Z",
            "due_date": "2025-11-15T18:00:00Z"
        }
        
        response = client.put(
            "/report-tracker/nonexistent-report-id",
            json=update_data
        )
        
        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_report_status(self, client, db):
        # Try to get status for a non-existent report
        response = client.get("/report-tracker/nonexistent-report-id/status")
        
        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_report_tracker(self, client, db):
        # Try to get a non-existent report
        response = client.get("/report-tracker/nonexistent-report-id")
        
        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()


class TestPathResolution:
    """Tests for dynamic transition path resolution functionality."""
    
    def test_resolve_simple_string_transition(self):
        """Test that simple string transitions are returned as-is."""
        from app.services.report_tracker_service import ReportTrackerService
        
        result = ReportTrackerService._resolve_transition_path("next_step", None, "success_goto")
        assert result == "next_step"
    
    def test_resolve_simple_string_with_path_provided(self):
        """Test that simple string transitions ignore the path."""
        from app.services.report_tracker_service import ReportTrackerService
        
        result = ReportTrackerService._resolve_transition_path("next_step", "some/path", "success_goto")
        assert result == "next_step"
    
    def test_resolve_nested_dict_with_default(self):
        """Test that nested dict returns default when no path provided."""
        from app.services.report_tracker_service import ReportTrackerService
        
        transition = {
            "default": "standard_step",
            "exemption": "exemption_step"
        }
        result = ReportTrackerService._resolve_transition_path(transition, None, "success_goto")
        assert result == "standard_step"
    
    def test_resolve_nested_dict_with_path(self):
        """Test that nested dict resolves path correctly."""
        from app.services.report_tracker_service import ReportTrackerService
        
        transition = {
            "default": "standard_step",
            "exemption": "exemption_step",
            "fast_track": "priority_step"
        }
        result = ReportTrackerService._resolve_transition_path(transition, "exemption", "success_goto")
        assert result == "exemption_step"
        
        result = ReportTrackerService._resolve_transition_path(transition, "fast_track", "success_goto")
        assert result == "priority_step"
    
    def test_resolve_deeply_nested_path(self):
        """Test that deeply nested paths are resolved correctly."""
        from app.services.report_tracker_service import ReportTrackerService
        
        transition = {
            "default": "standard_step",
            "exemption": {
                "std": "std_exemption_step",
                "errc": "errc_review_step",
                "reject": "external_review_step"
            }
        }
        result = ReportTrackerService._resolve_transition_path(transition, "exemption/errc", "success_goto")
        assert result == "errc_review_step"
        
        result = ReportTrackerService._resolve_transition_path(transition, "exemption/std", "success_goto")
        assert result == "std_exemption_step"
    
    def test_resolve_invalid_path_raises_error(self):
        """Test that invalid path raises UnprocessableEntityException."""
        from app.services.report_tracker_service import ReportTrackerService
        from app.exceptions import UnprocessableEntityException
        
        transition = {
            "default": "standard_step",
            "exemption": "exemption_step"
        }
        
        with pytest.raises(UnprocessableEntityException) as exc_info:
            ReportTrackerService._resolve_transition_path(transition, "invalid_key", "success_goto")
        
        assert str(exc_info.value.detail) == "invalid path:invalid_key. available options:exemption"
    
    def test_resolve_missing_default_raises_error(self):
        """Test that missing default key raises error when no path provided."""
        from app.services.report_tracker_service import ReportTrackerService
        from app.exceptions import UnprocessableEntityException
        
        transition = {
            "exemption": "exemption_step",
            "fast_track": "priority_step"
        }
        
        with pytest.raises(UnprocessableEntityException) as exc_info:
            ReportTrackerService._resolve_transition_path(transition, None, "success_goto")
        
        assert "default" in str(exc_info.value.detail).lower()
    
    def test_get_default_transition_simple_string(self):
        """Test _get_default_transition with simple string."""
        from app.services.report_tracker_service import ReportTrackerService
        
        result = ReportTrackerService._get_default_transition("next_step")
        assert result == "next_step"
    
    def test_get_default_transition_nested_dict(self):
        """Test _get_default_transition with nested dict."""
        from app.services.report_tracker_service import ReportTrackerService
        
        transition = {
            "default": "standard_step",
            "exemption": "exemption_step"
        }
        result = ReportTrackerService._get_default_transition(transition)
        assert result == "standard_step"
    
    def test_get_default_transition_deeply_nested(self):
        """Test _get_default_transition with deeply nested default."""
        from app.services.report_tracker_service import ReportTrackerService
        
        transition = {
            "default": {
                "default": "deeply_nested_default"
            },
            "exemption": "exemption_step"
        }
        result = ReportTrackerService._get_default_transition(transition)
        assert result == "deeply_nested_default"
    
    def test_get_default_transition_returns_none_for_missing(self):
        """Test _get_default_transition returns None when no default exists."""
        from app.services.report_tracker_service import ReportTrackerService
        
        transition = {
            "exemption": "exemption_step"
        }
        result = ReportTrackerService._get_default_transition(transition)
        assert result is None


class TestWorkflowActions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", [
        "accept", "submit", "approve",  # Forward actions
        "reject", "push_back", "pull_back"  # Backward actions
    ])
    async def test_all_action_types(self, client, db, action):
        """Test supported navigation action types work correctly."""
        # First ensure we have content products
        await _create_test_content_products(db)
        
        # Create a report
        report_data = {
            "report_id": f"PR-{action}-test",
            "content_product_name": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB
        }
        create_response = client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]
        
        # For backward actions, move forward once to have an in-progress step
        if WorkflowActionType.is_backward_action(action):
            warmup_response = client.put(f"/report-tracker/{report_id}", json={"action": "accept"})
            assert warmup_response.status_code == status.HTTP_200_OK

        # Update with the action
        update_data = {"action": action}
        response = client.put(f"/report-tracker/{report_id}", json=update_data)
        
        # Should succeed
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "workflow_steps_json" in data
    
    @pytest.mark.asyncio
    async def test_forward_actions_behavior(self, client, db):
        """Test that all forward actions (accept, submit, approve) behave the same."""
        await _create_test_content_products(db)
        
        forward_actions = ["accept", "submit", "approve"]
        results = []
        
        for action in forward_actions:
            # Create a new report for each test
            report_data = {
                "report_id": f"PR-forward-{action}",
                "content_product_name": "Credit Opinion",
                "lob": DEFAULT_LOB,
                "sub_lob": DEFAULT_SUB_LOB
            }
            create_response = client.post("/report-tracker/", json=report_data)
            report_id = create_response.json()["report_id"]
            
            # Apply the action
            update_data = {"action": action}
            response = client.put(f"/report-tracker/{report_id}", json=update_data)
            assert response.status_code == status.HTTP_200_OK
            
            # Get the status to verify behavior
            status_response = client.get(f"/report-tracker/{report_id}/status")
            results.append(status_response.json())
        
        # All forward actions should produce similar results
        # (completed first step, moved to next step)
        assert len(results) == 3
        # Basic structure check - all should have progress_tracker
        for result in results:
            assert "progress_tracker" in result
    
    @pytest.mark.asyncio
    async def test_backward_actions_behavior(self, client, db):
        """Test that all backward actions (reject, push_back, pull_back) behave the same."""
        await _create_test_content_products(db)
        
        backward_actions = ["reject", "push_back", "pull_back"]
        results = []
        
        for action in backward_actions:
            # Create a new report and move it forward first
            report_data = {
                "report_id": f"PR-backward-{action}",
                "content_product_name": "Credit Opinion",
                "lob": DEFAULT_LOB,
                "sub_lob": DEFAULT_SUB_LOB
            }
            create_response = client.post("/report-tracker/", json=report_data)
            report_id = create_response.json()["report_id"]
            
            # Move forward first
            client.put(f"/report-tracker/{report_id}", json={"action": "accept"})
            
            # Apply the backward action
            update_data = {"action": action}
            response = client.put(f"/report-tracker/{report_id}", json=update_data)
            assert response.status_code == status.HTTP_200_OK
            
            # Get the status to verify behavior
            status_response = client.get(f"/report-tracker/{report_id}/status")
            results.append(status_response.json())
        
        # All backward actions should produce similar results
        assert len(results) == 3
        # Basic structure check - all should have progress_tracker
        for result in results:
            assert "progress_tracker" in result
    
    @pytest.mark.asyncio
    async def test_invalid_action_type(self, client, db):
        """Test that invalid action types are rejected."""
        await _create_test_content_products(db)
        
        # Create a report
        report_data = {
            "report_id": "PR-invalid-action",
            "content_product_name": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB
        }
        create_response = client.post("/report-tracker/", json=report_data)
        report_id = create_response.json()["report_id"]
        
        # Try invalid action
        update_data = {"action": "invalid_action"}
        response = client.put(f"/report-tracker/{report_id}", json=update_data)
        
        # Should return 422 validation error
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
