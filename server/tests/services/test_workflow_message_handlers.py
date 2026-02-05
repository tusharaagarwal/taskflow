"""
Unit tests for WorkflowMessageHandlers.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.workflow_message_handlers import (
    WorkflowMessageHandlers,
    register_message_handlers,
)


class TestWorkflowMessageHandlers:
    """Tests for WorkflowMessageHandlers class."""

    def test_init(self):
        """Test handler initialization."""
        handlers = WorkflowMessageHandlers()
        assert handlers.report_tracker_service is not None

    @pytest.mark.asyncio
    async def test_handle_assembler_completion_missing_report_id(self):
        """Test handling completion message without report_id."""
        handlers = WorkflowMessageHandlers()

        await handlers.handle_assembler_completion({})

        # Should not raise, just log error

    @pytest.mark.asyncio
    @patch("app.services.workflow_message_handlers.aws_messaging_service")
    async def test_handle_assembler_completion_success(self, mock_aws):
        """Test successful assembler completion handling."""
        mock_aws.publish_report_update = AsyncMock()

        handlers = WorkflowMessageHandlers()
        handlers.report_tracker_service.update_report = AsyncMock(return_value=True)

        await handlers.handle_assembler_completion({"report_id": "REP-001"})

        handlers.report_tracker_service.update_report.assert_called()

    @pytest.mark.asyncio
    async def test_handle_endpoint_pr_event_missing_pr_id(self):
        """Test handling PR event without pr_id."""
        handlers = WorkflowMessageHandlers()

        await handlers.handle_endpoint_pr_event({})

        # Should not raise

    @pytest.mark.asyncio
    async def test_handle_endpoint_pr_event_non_approved(self):
        """Test handling non-approved PR event."""
        handlers = WorkflowMessageHandlers()

        await handlers.handle_endpoint_pr_event(
            {"pr_id": "PR-001", "event_type": "rejected"}
        )

        # Should not raise, just log

    @pytest.mark.asyncio
    @patch("app.services.workflow_message_handlers.aws_messaging_service")
    async def test_trigger_second_step_processing(self, mock_aws):
        """Test triggering second step processing."""
        mock_aws.publish_report_update = AsyncMock()

        handlers = WorkflowMessageHandlers()
        handlers.report_tracker_service.update_report = AsyncMock()

        await handlers._trigger_second_step_processing("REP-001")

        mock_aws.publish_report_update.assert_called()

    @pytest.mark.asyncio
    async def test_handle_exception_in_completion(self):
        """Test exception handling in completion handler."""
        handlers = WorkflowMessageHandlers()
        handlers.report_tracker_service.update_report = AsyncMock(
            side_effect=Exception("DB Error")
        )

        await handlers.handle_assembler_completion({"report_id": "REP-001"})

        # Should not raise


class TestRegisterMessageHandlers:
    """Tests for handler registration."""

    @patch("app.services.workflow_message_handlers.aws_messaging_service")
    def test_register_message_handlers(self, mock_aws):
        """Test that all handlers are registered."""
        mock_aws.register_handler = MagicMock()

        register_message_handlers()

        assert mock_aws.register_handler.call_count == 2
