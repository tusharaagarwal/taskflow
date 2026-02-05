import pytest
import pytest_asyncio
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from fastapi import FastAPI
from app.db.database import Base, get_db
from app.routers.v1.abbreviation import router as abbreviation_router

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test app
mock_app = FastAPI()
mock_app.include_router(abbreviation_router)

@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    policy = asyncio.WindowsSelectorEventLoopPolicy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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

@pytest_asyncio.fixture(scope="function")
async def client(db):
    async def override_get_db():
        try:
            yield db
        finally:
            await db.close()
    
    mock_app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(mock_app) as test_client:
        yield test_client
    
    mock_app.dependency_overrides.clear()

class TestAbbreviation:
    @pytest.mark.asyncio
    async def test_create_abbreviation(self, client, db):
        """Test creating a new abbreviation."""
        abbreviation_data = {
            "document_type": "Test Document",
            "abbreviation": "TD",
            "is_active": True
        }
        
        response = client.post("/abbreviation/", json=abbreviation_data)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["document_type"] == "Test Document"
        assert data["abbreviation"] == "TD"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_duplicate_abbreviation(self, client, db):
        """Test creating duplicate abbreviation returns 409."""
        # First abbreviation
        abbreviation_data = {
            "document_type": "Duplicate Test",
            "abbreviation": "DT",
            "is_active": True
        }
        
        response1 = client.post("/abbreviation/", json=abbreviation_data)
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Duplicate abbreviation
        response2 = client.post("/abbreviation/", json=abbreviation_data)
        assert response2.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_abbreviations(self, client, db):
        """Test listing all abbreviations."""
        # Create test data
        abbreviations = [
            {"document_type": "Doc 1", "abbreviation": "D1", "is_active": True},
            {"document_type": "Doc 2", "abbreviation": "D2", "is_active": False},
            {"document_type": "Doc 3", "abbreviation": "D3", "is_active": True}
        ]
        
        for abbr in abbreviations:
            client.post("/abbreviation/", json=abbr)
        
        # Test list all (defaults to active only)
        response = client.get("/abbreviation/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2  # Only active items by default
        
        # Test list all including inactive
        response = client.get("/abbreviation/?active_only=false")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 3  # All items
        
        # Test active only explicitly
        response = client.get("/abbreviation/?active_only=true")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        assert all(abbr["is_active"] for abbr in data)

    @pytest.mark.asyncio
    async def test_get_abbreviation_by_document_type(self, client, db):
        """Test getting abbreviation by document type."""
        # Create test data
        abbreviation_data = {
            "document_type": "Get Test",
            "abbreviation": "GT",
            "is_active": True
        }
        
        create_response = client.post("/abbreviation/", json=abbreviation_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        
        # Get by document type
        response = client.get("/abbreviation/Get Test")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["document_type"] == "Get Test"
        assert data["abbreviation"] == "GT"

    @pytest.mark.asyncio
    async def test_get_nonexistent_abbreviation(self, client, db):
        """Test getting non-existent abbreviation returns 404."""
        response = client.get("/abbreviation/Nonexistent")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_abbreviation(self, client, db):
        """Test updating an abbreviation."""
        # Create test data
        abbreviation_data = {
            "document_type": "Update Test",
            "abbreviation": "UT",
            "is_active": True
        }
        
        create_response = client.post("/abbreviation/", json=abbreviation_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        
        # Update abbreviation
        update_data = {
            "abbreviation": "UPDATED",
            "is_active": False
        }
        
        response = client.put("/abbreviation/Update Test", json=update_data)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["abbreviation"] == "UPDATED"
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_nonexistent_abbreviation(self, client, db):
        """Test updating non-existent abbreviation returns 404."""
        update_data = {
            "abbreviation": "UPDATED",
            "is_active": False
        }
        
        response = client.put("/abbreviation/Nonexistent", json=update_data)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_abbreviation(self, client, db):
        """Test deleting an abbreviation."""
        # Create test data
        abbreviation_data = {
            "document_type": "Delete Test",
            "abbreviation": "DT",
            "is_active": True
        }
        
        create_response = client.post("/abbreviation/", json=abbreviation_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        
        # Delete abbreviation
        response = client.delete("/abbreviation/Delete Test")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify deletion
        get_response = client.get("/abbreviation/Delete Test")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_nonexistent_abbreviation(self, client, db):
        """Test deleting non-existent abbreviation returns 404."""
        response = client.delete("/abbreviation/Nonexistent")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_lookup_abbreviation_found(self, client, db):
        """Test looking up existing abbreviation."""
        # Create test data
        abbreviation_data = {
            "document_type": "Lookup Test",
            "abbreviation": "LT",
            "is_active": True
        }
        
        client.post("/abbreviation/", json=abbreviation_data)
        
        # Lookup abbreviation
        lookup_data = {"document_type": "Lookup Test"}
        response = client.post("/abbreviation/lookup", json=lookup_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["document_type"] == "Lookup Test"
        assert data["abbreviation"] == "LT"
        assert data["found"] is True

    @pytest.mark.asyncio
    async def test_lookup_abbreviation_not_found(self, client, db):
        """Test looking up non-existent abbreviation."""
        lookup_data = {"document_type": "Nonexistent"}
        response = client.post("/abbreviation/lookup", json=lookup_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["document_type"] == "Nonexistent"
        assert data["abbreviation"] == ""
        assert data["found"] is False

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, client):
        """Test getting cache statistics."""
        response = client.get("/abbreviation/cache/stats")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "hits" in data
        assert "misses" in data
        assert "hit_rate" in data
        assert "size" in data
        assert "max_size" in data
        assert "ttl_seconds" in data
        assert "enabled" in data

    @pytest.mark.asyncio
    async def test_invalidate_cache_all(self, client):
        """Test invalidating entire cache."""
        invalidate_data = {}
        response = client.post("/abbreviation/cache/invalidate", json=invalidate_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "invalidated_count" in data
        assert "message" in data
        assert "Invalidated" in data["message"]

    @pytest.mark.asyncio
    async def test_invalidate_cache_specific(self, client):
        """Test invalidating specific cache entry."""
        invalidate_data = {"document_type": "Test Document"}
        response = client.post("/abbreviation/cache/invalidate", json=invalidate_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "invalidated_count" in data
        assert "message" in data
        assert "Test Document" in data["message"]

    @pytest.mark.asyncio
    async def test_cleanup_cache(self, client):
        """Test cleaning up expired cache entries."""
        response = client.post("/abbreviation/cache/cleanup")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "invalidated_count" in data
        assert "message" in data
        assert "expired" in data["message"]

    @pytest.mark.asyncio
    async def test_create_abbreviation_validation_error(self, client, db):
        """Test creating abbreviation with invalid data."""
        # Missing required fields
        invalid_data = {
            "abbreviation": "INV"
            # Missing document_type
        }
        
        response = client.post("/abbreviation/", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_create_abbreviation_too_long_abbreviation(self, client, db):
        """Test creating abbreviation with abbreviation too long."""
        invalid_data = {
            "document_type": "Test Document",
            "abbreviation": "TOO_LONG_ABBREVIATION",  # More than 10 characters
            "is_active": True
        }
        
        response = client.post("/abbreviation/", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
