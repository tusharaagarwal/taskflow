"""Unit and light integration tests for runtime app config service."""

import os
import sys

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.config.runtime_config_keys import DEFAULT_WORKFLOW_ID_KEY
from app.db.database import Base
from app.models.application_runtime_config import (
    ApplicationRuntimeConfig,
    RUNTIME_CONFIG_ROW_ID,
)
from app.services.runtime_app_config_service import (
    RuntimeAppConfigService,
    coerce_int_value,
    resolve_default_workflow_id_from_data,
    resolve_int_from_runtime_data_map,
)

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def test_resolve_int_from_runtime_data_map():
    assert (
        resolve_int_from_runtime_data_map(
            {"foo": 3}, "foo", code_fallback=99
        )
        == 3
    )
    assert (
        resolve_int_from_runtime_data_map(
            {"foo": "12"}, "foo", code_fallback=99
        )
        == 12
    )
    assert (
        resolve_int_from_runtime_data_map(
            {}, "foo", code_fallback=99
        )
        == 99
    )
    assert (
        resolve_int_from_runtime_data_map(
            None, "foo", code_fallback=88
        )
        == 88
    )


def test_resolve_default_workflow_id_from_data(monkeypatch):
    monkeypatch.setattr(
        "app.services.runtime_app_config_service.DEFAULT_WORKFLOW_ID_CODE_FALLBACK",
        7,
    )
    assert resolve_default_workflow_id_from_data({"default_workflow_id": 5}) == 5
    assert resolve_default_workflow_id_from_data({}) == 7


def test_coerce_int_value():
    assert coerce_int_value(5) == 5
    assert coerce_int_value("7") == 7
    assert coerce_int_value(" 42 ") == 42
    assert coerce_int_value(True) is None
    assert coerce_int_value(None) is None
    assert coerce_int_value("") is None
    assert coerce_int_value("nope") is None
    assert coerce_int_value(3.0) == 3
    assert coerce_int_value(3.5) is None


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


@pytest.mark.asyncio
async def test_get_effective_int_prefers_db(engine):
    async with async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )() as session:
        await RuntimeAppConfigService.patch_merge_data(
            session, {DEFAULT_WORKFLOW_ID_KEY: 42}
        )

    async with async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )() as session:
        v = await RuntimeAppConfigService.get_effective_int(
            session,
            DEFAULT_WORKFLOW_ID_KEY,
            code_fallback=1,
        )
        assert v == 42


@pytest.mark.asyncio
async def test_get_effective_int_uses_code_fallback(engine):
    async with async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )() as session:
        v = await RuntimeAppConfigService.get_effective_int(
            session,
            DEFAULT_WORKFLOW_ID_KEY,
            code_fallback=99,
        )
        assert v == 99
