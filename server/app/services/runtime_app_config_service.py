from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.runtime_config_defaults import DEFAULT_WORKFLOW_ID_CODE_FALLBACK
from app.config.runtime_config_keys import DEFAULT_WORKFLOW_ID_KEY
from app.models.application_runtime_config import (
    ApplicationRuntimeConfig,
    RUNTIME_CONFIG_ROW_ID,
)

logger = logging.getLogger(__name__)


def _normalize_data(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def coerce_int_value(value: Any) -> int | None:
    """Parse DB/JSON value to int; invalid or missing returns None (bool excluded)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def resolve_int_from_runtime_data_map(
    data: Any,
    key: str,
    *,
    code_fallback: int | None,
) -> int | None:
    """
    Read ``key`` from a runtime config ``data`` mapping (JSON object), coerce to int,
    otherwise return ``code_fallback``.
    """
    bucket = _normalize_data(data)
    raw = bucket.get(key)
    coerced = coerce_int_value(raw)
    if coerced is not None:
        return coerced
    if code_fallback is not None:
        logger.debug(
            "Runtime config key %s missing or invalid in data map; using code fallback %s",
            key,
            code_fallback,
        )
    else:
        logger.debug(
            "Runtime config key %s missing or invalid in data map; no code fallback",
            key,
        )
    return code_fallback


def resolve_default_workflow_id_from_data(data: Any) -> int | None:
    """Resolve ``default_workflow_id`` from the persisted ``data`` dict only (no DB I/O)."""
    return resolve_int_from_runtime_data_map(
        data,
        DEFAULT_WORKFLOW_ID_KEY,
        code_fallback=DEFAULT_WORKFLOW_ID_CODE_FALLBACK,
    )


class RuntimeAppConfigService:
    """DB singleton row (id=1) with JSON map; shallow merge on PATCH."""

    @staticmethod
    async def ensure_singleton(db: AsyncSession) -> ApplicationRuntimeConfig:
        row = await db.get(ApplicationRuntimeConfig, RUNTIME_CONFIG_ROW_ID)
        if row is None:
            row = ApplicationRuntimeConfig(id=RUNTIME_CONFIG_ROW_ID, data={})
            db.add(row)
            await db.flush()
        elif not isinstance(row.data, dict):
            row.data = {}
            await db.flush()
        return row

    @staticmethod
    async def get_record(db: AsyncSession) -> ApplicationRuntimeConfig:
        row = await RuntimeAppConfigService.ensure_singleton(db)
        await db.refresh(row)
        return row

    @staticmethod
    async def patch_merge_data(
        db: AsyncSession, partial: dict[str, Any]
    ) -> ApplicationRuntimeConfig:
        await RuntimeAppConfigService.ensure_singleton(db)
        stmt = select(ApplicationRuntimeConfig).where(
            ApplicationRuntimeConfig.id == RUNTIME_CONFIG_ROW_ID,
        )
        bind = db.bind
        if bind is not None and getattr(bind, "dialect", None) and bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()

        result = await db.execute(stmt)
        row = result.scalar_one()
        base = _normalize_data(row.data)
        merged = {**base, **partial}
        row.data = merged
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def get_raw(db: AsyncSession, key: str) -> Any | None:
        row = await RuntimeAppConfigService.ensure_singleton(db)
        data = _normalize_data(row.data)
        return data.get(key)

    @staticmethod
    async def get_effective_int(
        db: AsyncSession,
        key: str,
        *,
        code_fallback: int | None,
    ) -> int | None:
        row = await RuntimeAppConfigService.ensure_singleton(db)
        return resolve_int_from_runtime_data_map(
            row.data,
            key,
            code_fallback=code_fallback,
        )

    @staticmethod
    async def get_default_workflow_id(db: AsyncSession) -> int | None:
        """Load singleton row and resolve ``default_workflow_id`` from ``data`` then code fallback."""
        row = await RuntimeAppConfigService.ensure_singleton(db)
        return resolve_default_workflow_id_from_data(row.data)
