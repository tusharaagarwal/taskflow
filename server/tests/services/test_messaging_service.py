"""
Unit tests for MessagingService (app.services.aws.messaging_service).
Publisher and settings are mocked; no real boto3/SNS/SQS.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.aws.messaging_service import (
    MessagingService,
    MessagingServiceError,
    get_messaging_service,
)


@pytest.fixture
def mock_publisher():
    """MessagePublisher with publish_to_sns and send_to_sqs mocked."""
    pub = MagicMock()
    pub.publish_to_sns = MagicMock(return_value={"MessageId": "sns-123"})
    pub.send_to_sqs = MagicMock(return_value={"MessageId": "sqs-456"})
    return pub


# ----- notify_consumers -----


def test_notify_consumers_disabled_returns_skipped(mock_publisher):
    """When messaging_enabled is False, notify_consumers returns skipped and does not call publisher."""
    with patch("app.services.aws.messaging_service.settings") as mock_settings:
        mock_settings.messaging_enabled = False
        svc = MessagingService(publisher=mock_publisher)
        result = svc.notify_consumers(
            report_id="R-1",
            event_type="draft_completed",
        )
    assert result == {"status": "skipped", "reason": "messaging_disabled"}
    mock_publisher.publish_to_sns.assert_not_called()


def test_notify_consumers_success_publish_to_sns(mock_publisher):
    """When messaging enabled and publish_to_sns True, publisher.publish_to_sns is called and result returned."""
    with patch("app.services.aws.messaging_service.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        mock_settings.consumer_notification_topic_name = "consumer-topic"
        mock_settings.consumer_notification_message_group_id = "group-1"
        svc = MessagingService(publisher=mock_publisher)
        result = svc.notify_consumers(
            report_id="R-2",
            event_type="report_published",
            status="completed",
            additional_data={"key": "value"},
        )
    assert "sns_response" in result
    assert result["sns_response"]["MessageId"] == "sns-123"
    mock_publisher.publish_to_sns.assert_called_once()
    call_kw = mock_publisher.publish_to_sns.call_args[1]
    assert call_kw["topic_name"] == "consumer-topic"
    assert call_kw["message"]["report_id"] == "R-2"
    assert call_kw["message"]["type"] == "orchestrator"
    assert call_kw["message"]["queue_name"] == "orchestrator_to_workspace"
    assert call_kw["message"]["event_type"] == "report_published"
    assert call_kw["message"]["data"] == {"key": "value"}


def test_notify_consumers_sns_failure_records_error(mock_publisher):
    """When publish_to_sns raises, result contains sns_error and no re-raise."""
    mock_publisher.publish_to_sns.side_effect = Exception("SNS unavailable")
    with patch("app.services.aws.messaging_service.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        mock_settings.consumer_notification_topic_name = "topic"
        mock_settings.consumer_notification_message_group_id = "g1"
        svc = MessagingService(publisher=mock_publisher)
        result = svc.notify_consumers(
            report_id="R-3",
            event_type="event",
        )
    assert "sns_error" in result
    assert result["sns_error"] == "SNS unavailable"
    assert "sns_response" not in result


# ----- notify_assembler_to_start -----


def test_notify_assembler_to_start_disabled_returns_skipped(mock_publisher):
    """When messaging_enabled is False, notify_assembler_to_start returns skipped."""
    with patch("app.services.aws.messaging_service.settings") as mock_settings:
        mock_settings.messaging_enabled = False
        svc = MessagingService(publisher=mock_publisher)
        result = svc.notify_assembler_to_start(
            report_id="R-1",
            workflow_id="WF-1",
        )
    assert result == {"status": "skipped", "reason": "messaging_disabled"}
    mock_publisher.publish_to_sns.assert_not_called()


def test_notify_assembler_to_start_both_false_raises(mock_publisher):
    """When publish_to_sns and send_to_sqs are both False, raises MessagingServiceError."""
    with patch("app.services.aws.messaging_service.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        svc = MessagingService(publisher=mock_publisher)
        with pytest.raises(MessagingServiceError) as exc_info:
            svc.notify_assembler_to_start(
                report_id="R-1",
                workflow_id="WF-1",
                publish_to_sns=False,
                send_to_sqs=False,
            )
    assert "At least one" in str(exc_info.value)


def test_notify_assembler_to_start_success_sns_and_sqs(mock_publisher):
    """When both publish_to_sns and send_to_sqs True, both publisher methods called."""
    with patch("app.services.aws.messaging_service.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        mock_settings.assembler_task_topic_name = "task-topic"
        mock_settings.assembler_task_queue_name = "task-queue"
        mock_settings.assembler_message_group_id = "mg-1"
        svc = MessagingService(publisher=mock_publisher)
        result = svc.notify_assembler_to_start(
            report_id="R-A",
            workflow_id="WF-1",
            pr_id="PR-1",
        )
    assert "sns_response" in result
    assert "sqs_response" in result
    mock_publisher.publish_to_sns.assert_called_once()
    mock_publisher.send_to_sqs.assert_called_once()
    call_msg = mock_publisher.publish_to_sns.call_args[1]["message"]
    assert call_msg["report_id"] == "R-A"
    assert call_msg["workflow_id"] == "WF-1"
    assert call_msg["pr_id"] == "PR-1"
    assert call_msg["type"] == "assembler_task"


# ----- get_messaging_service singleton -----


def test_get_messaging_service_returns_singleton():
    """get_messaging_service returns the same instance on multiple calls."""
    with patch("app.services.aws.messaging_service._messaging_service_instance", None):
        a = get_messaging_service()
        b = get_messaging_service()
    assert a is b


# ----- no-op methods (smoke) -----


def test_start_assembler_completion_listener_disabled_no_op(mock_publisher):
    """When messaging disabled, start_assembler_completion_listener returns without error."""
    with patch("app.services.aws.messaging_service.settings") as mock_settings:
        mock_settings.messaging_enabled = False
        svc = MessagingService(publisher=mock_publisher)
        svc.start_assembler_completion_listener(handler=lambda p, m: True)


def test_stop_assembler_completion_listener_no_op(mock_publisher):
    """stop_assembler_completion_listener runs without error."""
    svc = MessagingService(publisher=mock_publisher)
    svc.stop_assembler_completion_listener()
