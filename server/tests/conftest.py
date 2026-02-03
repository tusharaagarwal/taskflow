import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import text
import os
import sys
from datetime import datetime, timezone

# Add the server directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.db.database import Base, get_db
from app.models.content_product import ContentProduct
from app.models.report_tracker import ReportTracker
from app.models.workflow import Workflow

# Test database URL - using SQLite in-memory for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Sample test data
SAMPLE_CONTENT_PRODUCTS = [
    {"id": 1, "name": "Credit Opinion", "workflow_id": 1},
    {"id": 2, "name": "Research Update", "workflow_id": 2},
]

SAMPLE_WORKFLOWS = [
    {"workflow_id": 1, "workflow_json": "{\"stages\":[{\"stage_id\":1,\"name\":\"Draft\"}]}"},
    {"workflow_id": 2, "workflow_json": "{\"stages\":[{\"stage_id\":1,\"name\":\"Review\"}]}"},
]

SAMPLE_REPORT_TRACKERS = [
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "report_id": "REP-001",
        "workflow_json": "{}",
        "workflow_steps_json": "{}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    },
    {
        "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "report_id": "REP-002",
        "workflow_json": "{}",
        "workflow_steps_json": "{}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
]

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def engine():
    """Create a test database engine with SQLite in-memory."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=True,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"public": None}}
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Clean up
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()

@pytest.fixture
def app():
    """Create a FastAPI application for testing."""
    return app

@pytest.fixture
async def db(engine):
    """Create a test database session."""
    async with engine.connect() as conn:
        # Start a transaction
        transaction = await conn.begin()
        
        # Create a session bound to the connection
        async_session = sessionmaker(
            bind=conn, expire_on_commit=False, class_=AsyncSession
        )
        async with async_session() as session:
            yield session
            # Rollback the session-level transaction (if any left)
            await session.rollback()
        
        # Rollback the connection-level transaction
        await transaction.rollback()

@pytest.fixture
def client(db):
    """Create a test client that uses the test database."""
    # Override the get_db dependency
    async def override_get_db():
        try:
            yield db
        finally:
            await db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    # Clear overrides
    app.dependency_overrides.clear()

@pytest.fixture
async def test_content_products(db):
    """Load test content products into the database."""
    products = []
    for product_data in SAMPLE_CONTENT_PRODUCTS:
        product = ContentProduct(**product_data)
        db.add(product)
        products.append(product)
    
    await db.commit()
    
    # Refresh the instances to get any database-generated values
    for product in products:
        await db.refresh(product)
    
    return products

@pytest.fixture
async def test_workflows(db):
    """Load test workflows into the database."""
    workflows = []
    for workflow_data in SAMPLE_WORKFLOWS:
        workflow = Workflow(**workflow_data)
        db.add(workflow)
        workflows.append(workflow)
    
    await db.commit()
    
    # Refresh the instances to get any database-generated values
    for workflow in workflows:
        await db.refresh(workflow)
    
    return workflows

@pytest.fixture
async def test_report_trackers(db):
    """Load test report trackers into the database."""
    trackers = []
    for tracker_data in SAMPLE_REPORT_TRACKERS:
        tracker = ReportTracker(**tracker_data)
        db.add(tracker)
        trackers.append(tracker)
    
    await db.commit()
    
    # Refresh the instances to get any database-generated values
    for tracker in trackers:
        await db.refresh(tracker)
    
    return trackers

@pytest.fixture
async def test_data(db, test_content_products, test_workflows, test_report_trackers):
    """Load all test data into the database."""
    return {
        "content_products": test_content_products,
        "workflows": test_workflows,
        "report_trackers": test_report_trackers
    }
