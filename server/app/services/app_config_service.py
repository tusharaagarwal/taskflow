"""Simple service to read values from the application_runtime_config singleton row."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from config_loader import config

logger = logging.getLogger(__name__)

_db_url: str | None = None


def _get_sync_db_url() -> str:
    global _db_url
    if _db_url is None:
        _db_url = config.get_database_url()
        _db_url = _db_url.replace("postgresql+asyncpg://", "postgresql://")
    return _db_url


def get_config_value(key: str, fallback: Any = None) -> Any:
    """
    Read ``key`` from the ``application_runtime_config`` singleton ``data`` JSON map.

    Returns ``fallback`` if the row is missing, ``data`` is not a dict,
    or the key is absent — without inspecting the value's type.
    """
    try:
        engine = create_engine(
            _get_sync_db_url(),
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT data FROM application_runtime_config WHERE id = 1"),
            ).fetchone()
        engine.dispose()
        if row is None:
            logger.debug("Runtime config row not found; using fallback for key=%s", key)
            return fallback
        data = row[0]
        if isinstance(data, str):
            import json
            data = json.loads(data)
        if not isinstance(data, dict):
            return fallback
        return data.get(key, fallback)
    except Exception as exc:
        logger.warning("Failed to read runtime config key=%s: %s; using fallback", key, exc)
        return fallback
