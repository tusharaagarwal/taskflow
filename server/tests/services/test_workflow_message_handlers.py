"""
Unit tests for WorkflowMessageHandlers.
DB and messaging are mocked; tests cover success paths and error paths.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.workflow_message_handlers import (
    WorkflowMessageHandlers,
    register_message_handlers,
)


@pytest.fixture
def mock_report_tracker_service():
    """ReportTrackerService with update_report and create_report mocked."""
    with patch(
        "app.services.workflow_message_handlers.ReportTrackerService",
    ) as mock_cls:
        instance = MagicMock()
        instance.update_report = AsyncMock(return_value=True)
        instance.create_report = AsyncMock(return_value={"id": "R-123"})
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_messaging_service():
    """get_messaging_service returns a mock that has notify_consumers."""
    mock_svc = MagicMock()
    mock_svc.notify_consumers = MagicMock(return_value=None)
    with patch(
        "app.services.workflow_message_handlers.get_messaging_service",
        return_value=mock_svc,
    ):
        yield mock_svc


@pytest.mark.asyncio
async def test_handle_assembler_completion_no_report_id_returns_early(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When message has no report_id, handler returns without updating or notifying."""
    handlers = WorkflowMessageHandlers()
    await handlers.handle_assembler_completion({"event": "done"})
    mock_report_tracker_service.update_report.assert_not_called()
    mock_messaging_service.notify_consumers.assert_not_called()


@pytest.mark.asyncio
async def test_handle_assembler_completion_success(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When report_id present and update succeeds, handler updates, notifies, and triggers second step."""
    mock_report_tracker_service.update_report = AsyncMock(return_value=True)
    handlers = WorkflowMessageHandlers()
    with patch.object(
        handlers,
        "_trigger_second_step_processing",
        new_callable=AsyncMock,
    ) as mock_trigger:
        await handlers.handle_assembler_completion({"report_id": "R-456"})

    mock_report_tracker_service.update_report.assert_called_once()
    call_args = mock_report_tracker_service.update_report.call_args[0]
    assert call_args[0] == "R-456"
    assert call_args[1]["status"] == "first_draft_completed"
    assert "assembler_completed_at" in call_args[1]

    mock_messaging_service.notify_consumers.assert_called_once()
    notify_kw = mock_messaging_service.notify_consumers.call_args[1]
    assert notify_kw["report_id"] == "R-456"
    assert notify_kw["event_type"] == "assembler_completion"

    mock_trigger.assert_called_once_with("R-456")


@pytest.mark.asyncio
async def test_handle_assembler_completion_update_fails_no_notify(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When update_report returns False, handler does not notify or trigger second step."""
    mock_report_tracker_service.update_report = AsyncMock(return_value=False)
    handlers = WorkflowMessageHandlers()
    with patch.object(
        handlers,
        "_trigger_second_step_processing",
        new_callable=AsyncMock,
    ) as mock_trigger:
        await handlers.handle_assembler_completion({"report_id": "R-789"})

    mock_report_tracker_service.update_report.assert_called_once()
    mock_messaging_service.notify_consumers.assert_not_called()
    mock_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_handle_assembler_completion_exception_logged(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When update_report raises, handler catches and does not re-raise."""
    mock_report_tracker_service.update_report = AsyncMock(
        side_effect=RuntimeError("db error")
    )
    handlers = WorkflowMessageHandlers()
    await handlers.handle_assembler_completion({"report_id": "R-1"})
    mock_messaging_service.notify_consumers.assert_not_called()


@pytest.mark.asyncio
async def test_handle_endpoint_pr_event_no_pr_id_returns_early(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When message has no pr_id, handler returns without starting report creation."""
    handlers = WorkflowMessageHandlers()
    await handlers.handle_endpoint_pr_event({"event_type": "approved"})
    mock_report_tracker_service.create_report.assert_not_called()


@pytest.mark.asyncio
async def test_handle_endpoint_pr_event_approved_calls_start_report_creation(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When event_type is approved, handler calls _start_report_creation."""
    handlers = WorkflowMessageHandlers()
    with patch.object(
        handlers,
        "_start_report_creation",
        new_callable=AsyncMock,
    ) as mock_start:
        await handlers.handle_endpoint_pr_event(
            {"pr_id": "PR-1", "event_type": "approved"}
        )
    mock_start.assert_called_once_with("PR-1")


@pytest.mark.asyncio
async def test_handle_endpoint_pr_event_non_approved_ignored(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When event_type is not approved, handler does not start report creation."""
    handlers = WorkflowMessageHandlers()
    with patch.object(
        handlers,
        "_start_report_creation",
        new_callable=AsyncMock,
    ) as mock_start:
        await handlers.handle_endpoint_pr_event(
            {"pr_id": "PR-2", "event_type": "rejected"}
        )
    mock_start.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_second_step_processing_calls_update_and_notify(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """_trigger_second_step_processing updates report and notifies consumers."""
    handlers = WorkflowMessageHandlers()
    await handlers._trigger_second_step_processing("R-999")

    mock_report_tracker_service.update_report.assert_called_once()
    call_args = mock_report_tracker_service.update_report.call_args[0]
    assert call_args[0] == "R-999"
    assert call_args[1]["status"] == "second_step_in_progress"

    mock_messaging_service.notify_consumers.assert_called_once()
    notify_kw = mock_messaging_service.notify_consumers.call_args[1]
    assert notify_kw["report_id"] == "R-999"
    assert notify_kw["event_type"] == "second_step_started"


@pytest.mark.asyncio
async def test_start_report_creation_success_notifies_and_triggers_first_draft(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When create_report returns a report, handler notifies and triggers first draft creation."""
    mock_report_tracker_service.create_report = AsyncMock(
        return_value={"id": "R-NEW", "pr_id": "PR-10"}
    )
    handlers = WorkflowMessageHandlers()
    with patch.object(
        handlers,
        "_trigger_first_draft_creation",
        new_callable=AsyncMock,
    ) as mock_trigger:
        await handlers._start_report_creation("PR-10")

    mock_report_tracker_service.create_report.assert_called_once()
    create_data = mock_report_tracker_service.create_report.call_args[0][0]
    assert create_data["pr_id"] == "PR-10"
    assert create_data["status"] == "report_creation_started"

    mock_messaging_service.notify_consumers.assert_called_once()
    notify_kw = mock_messaging_service.notify_consumers.call_args[1]
    assert notify_kw["report_id"] == "R-NEW"
    assert notify_kw["event_type"] == "report_created"

    mock_trigger.assert_called_once_with("R-NEW", "PR-10")


@pytest.mark.asyncio
async def test_start_report_creation_returns_none_no_notify(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """When create_report returns None, handler does not notify or trigger first draft."""
    mock_report_tracker_service.create_report = AsyncMock(return_value=None)
    handlers = WorkflowMessageHandlers()
    with patch.object(
        handlers,
        "_trigger_first_draft_creation",
        new_callable=AsyncMock,
    ) as mock_trigger:
        await handlers._start_report_creation("PR-20")

    mock_messaging_service.notify_consumers.assert_not_called()
    mock_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_first_draft_creation_calls_update_and_notify(
    mock_report_tracker_service,
    mock_messaging_service,
):
    """_trigger_first_draft_creation updates report and notifies consumers."""
    handlers = WorkflowMessageHandlers()
    await handlers._trigger_first_draft_creation("R-1", "PR-1")

    mock_report_tracker_service.update_report.assert_called_once()
    call_args = mock_report_tracker_service.update_report.call_args[0]
    assert call_args[0] == "R-1"
    assert call_args[1]["status"] == "first_draft_in_progress"

    mock_messaging_service.notify_consumers.assert_called_once()
    notify_kw = mock_messaging_service.notify_consumers.call_args[1]
    assert notify_kw["report_id"] == "R-1"
    assert notify_kw["event_type"] == "first_draft_started"
    assert notify_kw["additional_data"]["pr_id"] == "PR-1"


def test_register_message_handlers_no_op():
    """register_message_handlers runs without error (no-op)."""
    register_message_handlers()
