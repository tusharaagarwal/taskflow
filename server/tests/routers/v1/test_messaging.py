"""
Tests for the messaging API router (GET /messaging/status, POST /messaging/publish-report-update).
All tests patch settings and get_messaging_service to avoid real AWS/SQS.
Lifespan is patched so sqs_consumer.start/stop do not run (no real SQS).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app as fastapi_app


@pytest.fixture(autouse=True)
def _mock_sqs_consumer_lifespan():
    """Prevent app lifespan from starting/stopping real SQS consumer."""
    with patch("app.main.sqs_consumer") as mock_consumer:
        mock_consumer.start = AsyncMock(return_value=None)
        mock_consumer.stop = AsyncMock(return_value=None)
        yield


def test_get_messaging_status_disabled():
    """When messaging_enabled is False, status returns disabled with message."""
    with patch("app.routers.v1.messaging.settings") as mock_settings:
        mock_settings.messaging_enabled = False
        with TestClient(fastapi_app) as client:
            response = client.get("/v1/messaging/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert "disabled" in body["message"].lower()
    assert "sqs_consumer_note" in body


def test_get_messaging_status_healthy():
    """When messaging_enabled is True, status returns healthy and config keys."""
    with patch("app.routers.v1.messaging.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        mock_settings.aws_region = "ap-south-1"
        mock_settings.assembler_task_topic_name = "task-topic"
        mock_settings.assembler_completion_queue_name = "completion-queue"
        mock_settings.consumer_notification_topic_name = "notif-topic"
        with TestClient(fastapi_app) as client:
            response = client.get("/v1/messaging/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["sqs_consumer"] == "in_process"
    assert body["aws_connectivity"] == "connected"
    assert body["config"]["region"] == "ap-south-1"
    assert body["config"]["assembler_task_topic"] == "task-topic"
    assert body["config"]["assembler_completion_queue"] == "completion-queue"
    assert body["config"]["consumer_notification_topic"] == "notif-topic"


def test_get_messaging_status_healthy_default_region():
    """When aws_region is missing, config uses default ap-south-1."""
    with patch("app.routers.v1.messaging.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        del mock_settings.aws_region
        with TestClient(fastapi_app) as client:
            response = client.get("/v1/messaging/status")
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["region"] == "ap-south-1"


def test_get_messaging_status_exception_returns_500():
    """When an exception occurs in the handler, return 500 without leaking internals."""
    import builtins
    _real_getattr = builtins.getattr
    with patch("app.routers.v1.messaging.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        mock_settings.aws_region = "ap-south-1"
        mock_settings.assembler_task_topic_name = ""
        mock_settings.assembler_completion_queue_name = ""
        mock_settings.consumer_notification_topic_name = ""

        def getattr_raise(obj, name, default=None):
            if name == "aws_region":
                raise RuntimeError("internal")
            return _real_getattr(obj, name, default)

        with patch("app.routers.v1.messaging.getattr", getattr_raise):
            with TestClient(fastapi_app) as client:
                response = client.get("/v1/messaging/status")
    assert response.status_code == 500
    body = response.json()
    assert body.get("detail") == "Failed to get messaging status"


def test_get_messaging_status_exception_500_detail():
    """Exception in get_messaging_status returns 500 with generic detail."""
    import builtins
    _real_getattr = builtins.getattr
    with patch("app.routers.v1.messaging.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        mock_settings.assembler_task_topic_name = ""
        mock_settings.assembler_completion_queue_name = ""
        mock_settings.consumer_notification_topic_name = ""

        def getattr_raise(obj, name, default=None):
            if name == "aws_region":
                raise ValueError("oops")
            return _real_getattr(obj, name, default)

        with patch("app.routers.v1.messaging.getattr", getattr_raise):
            with TestClient(fastapi_app) as client:
                response = client.get("/v1/messaging/status")
    assert response.status_code == 500
    assert response.json().get("detail") == "Failed to get messaging status"


def test_publish_report_update_disabled_503():
    """When messaging is disabled, POST returns 503."""
    with patch("app.routers.v1.messaging.settings") as mock_settings:
        mock_settings.messaging_enabled = False
        with TestClient(fastapi_app) as client:
            response = client.post(
                "/v1/messaging/publish-report-update",
                params={"report_id": "R-1", "update_type": "completed"},
                json={"status": "completed"},
            )
    assert response.status_code == 503
    assert "disabled" in response.json().get("detail", "").lower()


def test_publish_report_update_success():
    """When messaging is enabled and service is mocked, POST returns 200 and correct body."""
    mock_svc = MagicMock()
    mock_svc.notify_consumers = MagicMock(return_value=None)
    with patch("app.routers.v1.messaging.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        with patch("app.routers.v1.messaging.get_messaging_service", return_value=mock_svc):
            with TestClient(fastapi_app) as client:
                response = client.post(
                    "/v1/messaging/publish-report-update",
                    params={"report_id": "R-123", "update_type": "published"},
                    json={"status": "published", "extra": "data"},
                )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Report update published successfully"
    assert body["report_id"] == "R-123"
    assert body["update_type"] == "published"
    mock_svc.notify_consumers.assert_called_once()
    call_kw = mock_svc.notify_consumers.call_args[1]
    assert call_kw["report_id"] == "R-123"
    assert call_kw["event_type"] == "published"
    assert call_kw["status"] == "published"
    assert call_kw["additional_data"] == {"status": "published", "extra": "data"}


def test_publish_report_update_notify_raises_500():
    """When notify_consumers raises, return 500 with generic detail."""
    mock_svc = MagicMock()
    mock_svc.notify_consumers.side_effect = Exception("backend error")
    with patch("app.routers.v1.messaging.settings") as mock_settings:
        mock_settings.messaging_enabled = True
        with patch("app.routers.v1.messaging.get_messaging_service", return_value=mock_svc):
            with TestClient(fastapi_app) as client:
                response = client.post(
                    "/v1/messaging/publish-report-update",
                    params={"report_id": "R-1", "update_type": "event"},
                    json={"status": "ok"},
                )
    assert response.status_code == 500
    assert response.json().get("detail") == "Failed to publish report update"
