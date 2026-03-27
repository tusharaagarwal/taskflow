"""Tests for GET/PATCH /v1/runtime-app-config."""

import asyncio
import os
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from app.db.database import Base, get_db
from app.models.application_runtime_config import (
    ApplicationRuntimeConfig,
    RUNTIME_CONFIG_ROW_ID,
)
from app.routers.v1.runtime_app_config import router as runtime_app_config_router

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
    async with async_sessionmaker(
        bind=eng, class_=AsyncSession, expire_on_commit=False
    )() as s:
        s.add(ApplicationRuntimeConfig(id=RUNTIME_CONFIG_ROW_ID, data={}))
        await s.commit()
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    async with async_sessionmaker(
        autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
    )() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db):
    app = FastAPI()
    app.include_router(runtime_app_config_router, prefix="/v1")

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestRuntimeAppConfigApi:
    def test_get_returns_empty_map(self, client):
        r = client.get("/v1/runtime-app-config/")
        assert r.status_code == status.HTTP_200_OK
        body = r.json()
        assert body["data"] == {}
        assert "updated_at" in body

    def test_patch_shallow_merge(self, client):
        r1 = client.patch(
            "/v1/runtime-app-config/",
            json={"data": {"default_workflow_id": 2, "x": "y"}},
        )
        assert r1.status_code == status.HTTP_200_OK
        assert r1.json()["data"]["default_workflow_id"] == 2
        assert r1.json()["data"]["x"] == "y"

        r2 = client.patch(
            "/v1/runtime-app-config/",
            json={"data": {"default_workflow_id": 99}},
        )
        assert r2.status_code == status.HTTP_200_OK
        assert r2.json()["data"]["default_workflow_id"] == 99
        assert r2.json()["data"]["x"] == "y"
