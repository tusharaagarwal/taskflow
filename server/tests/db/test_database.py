"""Unit tests for app.db.database (get_db dependency) and app.db.base_class."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_db_yields_session_and_closes():
    """get_db is an async generator that yields a session and closes it on exit."""
    from app.db.database import get_db

    mock_session = AsyncMock()
    mock_session.close = AsyncMock()

    async def mock_session_factory():
        return mock_session

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    with patch("app.db.database.AsyncSessionLocal", return_value=mock_cm):
        gen = get_db()
        session = await gen.__anext__()
        assert session is mock_session
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_db_closes_on_exception():
    """get_db closes session when consumer raises."""
    from app.db.database import get_db

    mock_session = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    with patch("app.db.database.AsyncSessionLocal", return_value=mock_cm):
        gen = get_db()
        await gen.__anext__()
        with pytest.raises(ValueError, match="test"):
            await gen.athrow(ValueError("test"))
        mock_session.close.assert_called_once()


def test_base_subclass_tablename():
    """Base.__tablename__ returns class name lowercased."""
    from app.models.report_tracker import ReportTracker
    assert ReportTracker.__tablename__ == "report_tracker"
