import pytest
import asyncio
import pytest_asyncio
from fastapi import status
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
from httpx import ASGITransport, AsyncClient
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
            "action_available": ["accept", "submit", "approve"],
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
            "action_available": ["accept", "submit", "approve", "reject", "push_back", "pull_back"],
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
            "action_available": ["accept", "submit", "approve", "reject", "push_back", "pull_back"],
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
mock_app = FastAPI()
mock_app.include_router(report_tracker_router)

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

    # Mock report ID generation to avoid Postgres sequence dependency in SQLite tests
    from app.services.report_tracker_service import ReportTrackerService
    async def mock_generate_id(db, document_type):
        import uuid
        # Return a deterministic ID for tests based on document_type but unique
        prefix = "CO" if "Credit" in document_type else "RPT"
        random_suffix = uuid.uuid4().hex[:6].upper()
        return f"{prefix}-{random_suffix}"
    
    monkeypatch.setattr(ReportTrackerService, "_generate_unique_report_id", mock_generate_id)

# This event_loop fixture is required for async tests
@pytest.fixture
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
            pass  # Session lifecycle managed by fixture

    mock_app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=mock_app),
        base_url="http://test",
    ) as ac:
        yield ac

    mock_app.dependency_overrides.clear()

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
        # Test data - Updated to new schema
        report_data = {
            "transaction_id": "TXN-12345",
            "pr_id": "PR-12345",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        
        # Make request
        response = await client.post("/report-tracker/", json=report_data)
        
        # Assertions
        if response.status_code != status.HTTP_201_CREATED:
            print(f"\n[DEBUG] Create failed: {response.status_code} - {response.text}\n")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["report_id"].startswith("CO-")  # Matches mocked ID format
        assert data["transaction_id"] == "TXN-12345"
        assert "workflow_steps_json" in data

    @pytest.mark.asyncio
    async def test_get_report_tracker(self, client, db):
        # First ensure we have content products
        await _create_test_content_products(db)
        
        # First create a report
        # First create a report
        report_data = {
            "transaction_id": "TXN-67890",
            "pr_id": "PR-67890",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        
        # Now get the report
        report_id = create_response.json()["report_id"]
        response = await client.get(f"/report-tracker/{report_id}")
        
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
            response = await client.put(
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
        response = await client.get(f"/report-tracker/{sample_report_tracker.report_id}/status")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["report_id"] == sample_report_tracker.report_id
        assert "progress_tracker" in data

    @pytest.mark.asyncio
    async def test_get_report_status_with_include_audit_param(self, client, sample_report_tracker):
        """Test status endpoint accepts include_audit query parameter."""
        # Test with include_audit=true
        response = await client.get(f"/report-tracker/{sample_report_tracker.report_id}/status?include_audit=true")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "progress_tracker" in data

        # Test with include_audit=false
        response = await client.get(f"/report-tracker/{sample_report_tracker.report_id}/status?include_audit=false")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "progress_tracker" in data

    @pytest.mark.asyncio
    async def test_get_report_workflow(self, client, sample_report_tracker):
        """Test getting workflow JSON for a report tracker."""
        # Get workflow
        response = await client.get(f"/report-tracker/{sample_report_tracker.report_id}/workflow")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["report_id"] == sample_report_tracker.report_id
        assert "workflow_json" in data
        assert data["workflow_json"] is not None
        assert "steps" in data["workflow_json"]
        assert len(data["workflow_json"]["steps"]) > 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_report_workflow(self, client, db):
        """Test getting workflow for a non-existent report."""
        response = await client.get("/report-tracker/nonexistent-report-id/workflow")

        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_report_trackers(self, client, db):
        # First ensure we have content products
        await _create_test_content_products(db)
        
        # Create a couple of reports
        # Create a couple of reports
        reports = [
            {
                "transaction_id": "TXN-11111", 
                "pr_id": "PR-11111", 
                "content_type": "Credit Opinion", 
                "lob": DEFAULT_LOB, 
                "sub_lob": DEFAULT_SUB_LOB,
                "document_type": "Credit Opinion",
                "action_code": "APPROVED"
            },
            {
                "transaction_id": "TXN-22222", 
                "pr_id": "PR-22222", 
                "content_type": "Credit Opinion", 
                "lob": DEFAULT_LOB, 
                "sub_lob": DEFAULT_SUB_LOB,
                "document_type": "Credit Opinion",
                "action_code": "APPROVED"
            }
        ]
        
        # Store created report IDs for later verification
        created_report_ids = []
        
        # Mock generator to return distinct IDs
        from app.services.report_tracker_service import ReportTrackerService
        original_mock = ReportTrackerService._generate_unique_report_id
        
        # Simple counter to ensure unique IDs
        counter = 0
        async def mock_seq_generator(db, dt):
            nonlocal counter
            counter += 1
            return f"CO-{100000+counter}"
            
        with patch.object(ReportTrackerService, '_generate_unique_report_id', side_effect=mock_seq_generator):
            for report in reports:
                response = await client.post("/report-tracker/", json=report)
                assert response.status_code == status.HTTP_201_CREATED
                created_report_ids.append(response.json()["report_id"])
        
        # List all reports
        response = await client.get("/report-tracker/")
        
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
        response = await client.get("/report-tracker/")
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
        
        response = await client.put(
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
        response = await client.get("/report-tracker/nonexistent-report-id/status")
        
        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_report_tracker(self, client, db):
        # Try to get a non-existent report
        response = await client.get("/report-tracker/nonexistent-report-id")
        
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
        # Create a report
        report_data = {
            "transaction_id": f"TXN-{action}",
            "pr_id": f"PR-{action}-test",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]
        
        # For backward actions, move forward once to have an in-progress step
        if WorkflowActionType.is_backward_action(action):
            warmup_response = await client.put(f"/report-tracker/{report_id}", json={"action": "accept"})
            assert warmup_response.status_code == status.HTTP_200_OK

        # Update with the action
        update_data = {"action": action}
        response = await client.put(f"/report-tracker/{report_id}", json=update_data)
        
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
            # Create a new report for each test
            report_data = {
                "transaction_id": f"TXN-fwd-{action}",
                "pr_id": f"PR-forward-{action}",
                "content_type": "Credit Opinion",
                "lob": DEFAULT_LOB,
                "sub_lob": DEFAULT_SUB_LOB,
                "document_type": "Credit Opinion",
                "action_code": "APPROVED"
            }
            create_response = await client.post("/report-tracker/", json=report_data)
            report_id = create_response.json()["report_id"]
            
            # Apply the action
            update_data = {"action": action}
            response = await client.put(f"/report-tracker/{report_id}", json=update_data)
            assert response.status_code == status.HTTP_200_OK
            
            # Get the status to verify behavior
            status_response = await client.get(f"/report-tracker/{report_id}/status")
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
            # Create a new report and move it forward first
            report_data = {
                "transaction_id": f"TXN-back-{action}",
                "pr_id": f"PR-backward-{action}",
                "content_type": "Credit Opinion",
                "lob": DEFAULT_LOB,
                "sub_lob": DEFAULT_SUB_LOB,
                "document_type": "Credit Opinion",
                "action_code": "APPROVED"
            }
            create_response = await client.post("/report-tracker/", json=report_data)
            report_id = create_response.json()["report_id"]
            
            # Move forward first
            await client.put(f"/report-tracker/{report_id}", json={"action": "accept"})
            
            # Apply the backward action
            update_data = {"action": action}
            response = await client.put(f"/report-tracker/{report_id}", json=update_data)
            assert response.status_code == status.HTTP_200_OK
            
            # Get the status to verify behavior
            status_response = await client.get(f"/report-tracker/{report_id}/status")
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
        # Create a report
        report_data = {
            "transaction_id": "TXN-invalid",
            "pr_id": "PR-invalid-action",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        report_id = create_response.json()["report_id"]
        
        # Try invalid action
        update_data = {"action": "invalid_action"}
        response = await client.put(f"/report-tracker/{report_id}", json=update_data)
        
        # Should return 422 validation error
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestAppDataUpdate:
    """Tests for app_data update functionality."""

    @pytest.mark.asyncio
    async def test_update_app_data_only_current_step(self, client, db):
        """Test updating app_data without action (updates current in-progress step)."""
        await _create_test_content_products(db)

        # Create a report
        # Create a report
        report_data = {
            "transaction_id": "TXN-app-data",
            "pr_id": "PR-app-data-only",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]

        # Update only app_data (no action)
        update_data = {
            "app_data": {
                "assignee": [{"user_id": "user-123", "name": "John Doe"}],
                "custom_field": "custom_value",
                "metadata": {"source": "test_app"}
            }
        }
        response = await client.put(f"/report-tracker/{report_id}", json=update_data)

        # Should succeed
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify app_data was updated on the current step
        progress_tracker = data["workflow_steps_json"]["progress_tracker"]
        current_step = next(s for s in progress_tracker if s["status"] == "in_progress")
        assert current_step["app_data"]["assignee"][0]["user_id"] == "user-123"
        assert current_step["app_data"]["custom_field"] == "custom_value"
        assert current_step["app_data"]["metadata"]["source"] == "test_app"

    @pytest.mark.asyncio
    async def test_update_app_data_with_instance_id(self, client, db):
        """Test updating app_data for a specific step using instance_id."""
        await _create_test_content_products(db)

        # Create a report
        report_data = {
            "transaction_id": "TXN-instance-id",
            "pr_id": "PR-instance-id-update",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]

        # Get the instance_id of the first step
        get_response = await client.get(f"/report-tracker/{report_id}/status")
        progress_tracker = get_response.json()["progress_tracker"]
        first_step_instance_id = progress_tracker[0]["instance_id"]

        # Update app_data using instance_id
        update_data = {
            "instance_id": first_step_instance_id,
            "app_data": {
                "reviewed": True,
                "review_notes": "Looks good"
            }
        }
        response = await client.put(f"/report-tracker/{report_id}", json=update_data)

        # Should succeed
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify app_data was updated on the specified step
        progress_tracker = data["workflow_steps_json"]["progress_tracker"]
        target_step = next(s for s in progress_tracker if s["instance_id"] == first_step_instance_id)
        assert target_step["app_data"]["reviewed"] == True
        assert target_step["app_data"]["review_notes"] == "Looks good"

    @pytest.mark.asyncio
    async def test_update_action_and_app_data_combined(self, client, db):
        """Test updating both action and app_data in a single request."""
        await _create_test_content_products(db)

        # Create a report
        report_data = {
            "transaction_id": "TXN-combined",
            "pr_id": "PR-combined-update",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]

        # Get the instance_id of the first step before action
        get_response = await client.get(f"/report-tracker/{report_id}/status")
        progress_tracker = get_response.json()["progress_tracker"]
        first_step_instance_id = progress_tracker[0]["instance_id"]

        # Update with action AND app_data
        update_data = {
            "action": "accept",
            "app_data": {
                "submitted_by": "jane@example.com",
                "submission_notes": "Ready for review"
            }
        }
        response = await client.put(f"/report-tracker/{report_id}", json=update_data)

        # Should succeed
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify the first step was completed (action worked)
        progress_tracker = data["workflow_steps_json"]["progress_tracker"]
        first_step = next(s for s in progress_tracker if s["instance_id"] == first_step_instance_id)
        assert first_step["status"] == "completed"

        # Verify app_data was updated on that step
        assert first_step["app_data"]["submitted_by"] == "jane@example.com"
        assert first_step["app_data"]["submission_notes"] == "Ready for review"

    @pytest.mark.asyncio
    async def test_update_empty_request_fails(self, client, db):
        """Test that empty request body (no action, no app_data) returns 422."""
        await _create_test_content_products(db)

        # Create a report
        report_data = {
            "transaction_id": "TXN-empty",
            "pr_id": "PR-empty-request",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]

        # Try empty update
        update_data = {}
        response = await client.put(f"/report-tracker/{report_id}", json=update_data)

        # Should return 422 validation error
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_update_invalid_instance_id_fails(self, client, db):
        """Test that invalid instance_id returns 422."""
        await _create_test_content_products(db)

        # Create a report
        report_data = {
            "transaction_id": "TXN-invalid",
            "pr_id": "PR-invalid-instance",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]

        # Try update with invalid instance_id
        update_data = {
            "instance_id": "non-existent-instance-id",
            "app_data": {"some": "data"}
        }
        response = await client.put(f"/report-tracker/{report_id}", json=update_data)

        # Should return 422 error
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_app_data_replaces_existing(self, client, db):
        """Test that app_data update completely replaces existing app_data."""
        await _create_test_content_products(db)

        # Create a report
        report_data = {
            "transaction_id": "TXN-replace",
            "pr_id": "PR-replace-app-data",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]

        # First update with some app_data
        update_data1 = {
            "app_data": {
                "field1": "value1",
                "field2": "value2"
            }
        }
        response1 = await client.put(f"/report-tracker/{report_id}", json=update_data1)
        assert response1.status_code == status.HTTP_200_OK

        # Second update with different app_data (should replace, not merge)
        update_data2 = {
            "app_data": {
                "field3": "value3"
            }
        }
        response2 = await client.put(f"/report-tracker/{report_id}", json=update_data2)
        assert response2.status_code == status.HTTP_200_OK

        # Verify app_data was replaced (not merged)
        progress_tracker = response2.json()["workflow_steps_json"]["progress_tracker"]
        current_step = next(s for s in progress_tracker if s["status"] == "in_progress")

        # Should only have field3, not field1 or field2
        assert "field3" in current_step["app_data"]
        assert current_step["app_data"]["field3"] == "value3"
        assert "field1" not in current_step["app_data"]
        assert "field2" not in current_step["app_data"]

    @pytest.mark.asyncio
    async def test_update_app_data_flexible_structure(self, client, db):
        """Test that app_data accepts any flexible structure."""
        await _create_test_content_products(db)

        # Create a report
        report_data = {
            "transaction_id": "TXN-flexible",
            "pr_id": "PR-flexible-app-data",
            "content_type": "Credit Opinion",
            "lob": DEFAULT_LOB,
            "sub_lob": DEFAULT_SUB_LOB,
            "document_type": "Credit Opinion",
            "action_code": "APPROVED"
        }
        create_response = await client.post("/report-tracker/", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["report_id"]

        # Update with complex nested app_data
        update_data = {
            "app_data": {
                "assignee": [
                    {"user_id": "u1", "name": "John", "email": "john@example.com"},
                    {"user_id": "u2", "name": "Jane", "role": "reviewer"}
                ],
                "metadata": {
                    "source": "crm_app",
                    "version": "2.0",
                    "nested": {
                        "level1": {
                            "level2": "deep_value"
                        }
                    }
                },
                "tags": ["urgent", "priority"],
                "count": 42,
                "active": True,
                "nullable_field": None
            }
        }
        response = await client.put(f"/report-tracker/{report_id}", json=update_data)

        # Should succeed
        assert response.status_code == status.HTTP_200_OK

        # Verify the complex structure was stored correctly
        progress_tracker = response.json()["workflow_steps_json"]["progress_tracker"]
        current_step = next(s for s in progress_tracker if s["status"] == "in_progress")
        app_data = current_step["app_data"]

        assert len(app_data["assignee"]) == 2
        assert app_data["metadata"]["nested"]["level1"]["level2"] == "deep_value"
        assert app_data["tags"] == ["urgent", "priority"]
        assert app_data["count"] == 42
        assert app_data["active"] == True
        assert app_data["nullable_field"] is None


class TestActionValidation:
    """Tests for action validation against workflow JSON action_available."""

    @pytest.mark.asyncio
    async def test_action_not_in_available_list(self, client, db):
        """Test that action not in action_available list is rejected."""
        await _create_test_content_products(db)

        # Create a workflow with specific action_available list
        workflow_with_actions = {
            "steps": [
                {
                    "step_id": "draft",
                    "step_name": "Initial Draft",
                    "stage_name": "Authoring",
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                    "action_available": ["submit", "approve"],  # Only submit and approve allowed
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
                    "action_available": ["approve", "reject"],
                    "personas": [],
                    "transitions": {
                        "success_goto": "publish",
                        "fail_goto": "draft"
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

        # Create report tracker directly in DB with custom workflow
        workflow_steps = ReportTrackerCreateRequest.create_workflow_steps_json(workflow_with_actions)
        tracker = ReportTracker(
            report_id="PR-action-validation",
            workflow_json=workflow_with_actions,
            workflow_steps_json=workflow_steps,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)

        # Try to use "accept" action which is not in action_available
        update_data = {"action": "accept"}
        response = await client.put(f"/report-tracker/{tracker.report_id}", json=update_data)

        # Should return 422 with clear error message
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert "detail" in data
        assert "not allowed" in data["detail"].lower()
        assert "accept" in data["detail"]
        assert "submit" in data["detail"]  # Should mention available actions
        assert "approve" in data["detail"]

    @pytest.mark.asyncio
    async def test_action_in_available_list_succeeds(self, client, db):
        """Test that action in action_available list is allowed."""
        await _create_test_content_products(db)

        # Create a workflow with specific action_available list
        workflow_with_actions = {
            "steps": [
                {
                    "step_id": "draft",
                    "step_name": "Initial Draft",
                    "stage_name": "Authoring",
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                    "action_available": ["accept", "submit", "approve"],
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
                    "action_available": ["approve", "reject"],
                    "personas": [],
                    "transitions": {
                        "success_goto": "publish",
                        "fail_goto": "draft"
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

        # Create report tracker directly in DB with custom workflow
        workflow_steps = ReportTrackerCreateRequest.create_workflow_steps_json(workflow_with_actions)
        tracker = ReportTracker(
            report_id="PR-action-allowed",
            workflow_json=workflow_with_actions,
            workflow_steps_json=workflow_steps,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)

        # Use "accept" action which IS in action_available
        update_data = {"action": "accept"}
        response = await client.put(f"/report-tracker/{tracker.report_id}", json=update_data)

        # Should succeed
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_empty_action_available_allows_all(self, client, db):
        """Test that empty action_available list allows all actions (corrected behavior)."""
        await _create_test_content_products(db)

        # Create a workflow with empty action_available list
        workflow_no_actions = {
            "steps": [
                {
                    "step_id": "draft",
                    "step_name": "Initial Draft",
                    "stage_name": "Authoring",
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                    "action_available": [],  # Empty list should allow all actions
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
                        "success_goto": "NA",
                        "fail_goto": "NA"
                    }
                }
            ]
        }

        # Create report tracker directly in DB with custom workflow
        workflow_steps = ReportTrackerCreateRequest.create_workflow_steps_json(workflow_no_actions)
        tracker = ReportTracker(
            report_id="PR-no-actions",
            workflow_json=workflow_no_actions,
            workflow_steps_json=workflow_steps,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)

        # Try any action - should be allowed
        update_data = {"action": "accept"}
        response = await client.put(f"/report-tracker/{tracker.report_id}", json=update_data)

        # Should return 200 (success) since empty action_available allows all actions
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_validation_uses_workflow_json_not_progress_tracker(self, client, db):
        """Test that validation uses workflow_json as source of truth, not progress_tracker."""
        await _create_test_content_products(db)

        # Create a workflow with specific actions
        workflow_with_actions = {
            "steps": [
                {
                    "step_id": "draft",
                    "step_name": "Initial Draft",
                    "stage_name": "Authoring",
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                    "action_available": ["submit"],  # Only submit in workflow JSON
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
                        "success_goto": "NA",
                        "fail_goto": "NA"
                    }
                }
            ]
        }

        # Create workflow_steps with DIFFERENT action_available (to test source of truth)
        workflow_steps = ReportTrackerCreateRequest.create_workflow_steps_json(workflow_with_actions)
        # Manually modify progress_tracker to have different actions (simulating data inconsistency)
        if workflow_steps.get("progress_tracker"):
            workflow_steps["progress_tracker"][0]["action_available"] = ["accept", "approve"]

        tracker = ReportTracker(
            report_id="PR-source-of-truth",
            workflow_json=workflow_with_actions,
            workflow_steps_json=workflow_steps,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)

        # Try "accept" which is in progress_tracker but NOT in workflow_json
        update_data = {"action": "accept"}
        response = await client.put(f"/report-tracker/{tracker.report_id}", json=update_data)

        # Should fail because workflow_json is the source of truth
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Try "submit" which IS in workflow_json
        update_data = {"action": "submit"}
        response = await client.put(f"/report-tracker/{tracker.report_id}", json=update_data)

        # Should succeed
        assert response.status_code == status.HTTP_200_OK


# Workflow with Assemble Draft then Initial Draft (for assembly -> Initial Draft test)
WORKFLOW_ASSEMBLY_TO_INITIAL = {
    "steps": [
        {
            "step_id": "initial_draft_001",
            "step_name": "Assemble Draft",
            "stage_name": "Authoring",
            "actor": {"role": "NA", "type": "agent"},
            "is_optional": False,
            "sla": {},
            "action_available": ["accept", "submit", "approve"],
            "transitions": {"success_goto": "initial_draft_002", "fail_goto": "NA"},
        },
        {
            "step_id": "initial_draft_002",
            "step_name": "Initial Draft",
            "stage_name": "Authoring",
            "actor": {"role": "gcc_associate", "type": "human"},
            "is_optional": False,
            "sla": {},
            "action_available": ["accept", "submit", "approve", "reject", "push_back", "pull_back"],
            "transitions": {"success_goto": "final_draft", "fail_goto": "initial_draft_001"},
        },
        {
            "step_id": "final_draft",
            "step_name": "Final Draft",
            "stage_name": "Content Assembly",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": ["accept", "submit", "approve", "reject", "push_back", "pull_back"],
            "transitions": {"success_goto": "NA", "fail_goto": "initial_draft_002"},
        },
    ]
}

# Workflow with optional Copy Edit (path=skip goes to finalize_report_pre_approval)
WORKFLOW_OPTIONAL_COPY_EDIT = {
    "steps": [
        {
            "step_id": "initial_draft_001",
            "step_name": "Assemble Draft",
            "stage_name": "Authoring",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": ["accept", "submit", "approve"],
            "transitions": {"success_goto": "initial_draft_002", "fail_goto": "NA"},
        },
        {
            "step_id": "initial_draft_002",
            "step_name": "Initial Draft",
            "stage_name": "Authoring",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": ["accept", "submit", "approve", "reject", "push_back", "pull_back"],
            "transitions": {"success_goto": "final_draft", "fail_goto": "initial_draft_001"},
        },
        {
            "step_id": "final_draft",
            "step_name": "Final Draft",
            "stage_name": "Content Assembly",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": ["accept", "submit", "approve", "reject", "push_back", "pull_back"],
            "transitions": {
                "success_goto": {"default": "copy_editing", "skip": "finalize_report_pre_approval"},
                "fail_goto": "initial_draft_002",
            },
        },
        {
            "step_id": "copy_editing",
            "step_name": "Copy Editing",
            "stage_name": "Editing",
            "actor": {"role": "copy_editor"},
            "is_optional": True,
            "sla": {},
            "action_available": ["accept", "submit", "approve", "reject", "push_back", "pull_back"],
            "transitions": {"success_goto": "finalize_report_pre_approval", "fail_goto": "final_draft"},
        },
        {
            "step_id": "finalize_report_pre_approval",
            "step_name": "Finalize Report",
            "stage_name": "Finalization",
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": ["accept", "submit", "approve"],
            "transitions": {"success_goto": "NA", "fail_goto": "copy_editing"},
        },
    ]
}


class TestFinalDraftUserStory:
    """Tests for Final Draft user story: assembly -> Initial Draft, optional Copy Edit skip, validation."""

    @pytest.mark.asyncio
    async def test_assembly_to_initial_draft_transition(self, client, db):
        """After completing Assemble Draft (accept), current step is Initial Draft."""
        await _create_test_content_products(db)
        workflow_steps = ReportTrackerCreateRequest.create_workflow_steps_json(WORKFLOW_ASSEMBLY_TO_INITIAL)
        tracker = ReportTracker(
            report_id="PR-assembly-initial",
            workflow_json=WORKFLOW_ASSEMBLY_TO_INITIAL,
            workflow_steps_json=workflow_steps,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)

        status_before = client.get(f"/report-tracker/{tracker.report_id}/status").json()
        current_before = next(
            (s for s in status_before["progress_tracker"] if s.get("status") == "in_progress"), None
        )
        assert current_before is not None
        assert current_before["step_id"] == "initial_draft_001"
        assert current_before["step_name"] == "Assemble Draft"

        response = client.put(
            f"/report-tracker/{tracker.report_id}",
            json={"action": "accept"},
        )
        assert response.status_code == status.HTTP_200_OK

        status_after = client.get(f"/report-tracker/{tracker.report_id}/status").json()
        current_after = next(
            (s for s in status_after["progress_tracker"] if s.get("status") == "in_progress"), None
        )
        assert current_after is not None
        assert current_after["step_id"] == "initial_draft_002"
        assert current_after["step_name"] == "Initial Draft"
        completed_assemble = next(
            (s for s in status_after["progress_tracker"] if s.get("step_id") == "initial_draft_001"), None
        )
        assert completed_assemble is not None
        assert completed_assemble["status"] == "completed"

    @pytest.mark.asyncio
    async def test_optional_copy_edit_skip(self, client, db):
        """With path=skip on Final Draft, transition skips Copy Editing to Finalize Report."""
        await _create_test_content_products(db)
        workflow_steps = ReportTrackerCreateRequest.create_workflow_steps_json(WORKFLOW_OPTIONAL_COPY_EDIT)
        tracker = ReportTracker(
            report_id="PR-optional-copy-skip",
            workflow_json=WORKFLOW_OPTIONAL_COPY_EDIT,
            workflow_steps_json=workflow_steps,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)

        for _ in range(2):
            client.put(f"/report-tracker/{tracker.report_id}", json={"action": "accept"})

        status_before = client.get(f"/report-tracker/{tracker.report_id}/status").json()
        current_before = next(
            (s for s in status_before["progress_tracker"] if s.get("status") == "in_progress"), None
        )
        assert current_before is not None
        assert current_before["step_id"] == "final_draft"

        response = client.put(
            f"/report-tracker/{tracker.report_id}",
            json={"action": "accept", "path": "skip"},
        )
        assert response.status_code == status.HTTP_200_OK

        status_after = client.get(f"/report-tracker/{tracker.report_id}/status").json()
        current_after = next(
            (s for s in status_after["progress_tracker"] if s.get("status") == "in_progress"), None
        )
        assert current_after is not None
        assert current_after["step_id"] == "finalize_report_pre_approval"
        copy_edit_step = next(
            (s for s in status_after["progress_tracker"] if s.get("step_id") == "copy_editing"), None
        )
        assert copy_edit_step is not None
        assert copy_edit_step["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_invalid_path_returns_422(self, client, db):
        """Invalid path (e.g. path=nonexistent when workflow has no such key) returns 422."""
        await _create_test_content_products(db)
        workflow_steps = ReportTrackerCreateRequest.create_workflow_steps_json(WORKFLOW_OPTIONAL_COPY_EDIT)
        tracker = ReportTracker(
            report_id="PR-invalid-path",
            workflow_json=WORKFLOW_OPTIONAL_COPY_EDIT,
            workflow_steps_json=workflow_steps,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)

        for _ in range(2):
            client.put(f"/report-tracker/{tracker.report_id}", json={"action": "accept"})
        response = client.put(
            f"/report-tracker/{tracker.report_id}",
            json={"action": "accept", "path": "nonexistent"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        detail = response.json().get("detail") or ""
        if isinstance(detail, list):
            detail = " ".join(str(d) for d in detail)
        detail = str(detail).lower()
        assert "path" in detail or "invalid" in detail
