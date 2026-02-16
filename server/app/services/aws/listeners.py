"""
Listeners for incoming AWS SQS messages.
This module provides background listeners for:
- Content Assembler completion notifications
"""
import logging
from typing import Any, Dict, Optional

import httpx
from app.config.config import settings
from app.services.aws.messaging_service import get_messaging_service

logger = logging.getLogger(__name__)


def handle_assembler_completion(payload: Dict[str, Any], message_id: str) -> bool:
    """
    Handle draft completion notification from Content Assembler.

    This function is called by the consumer when a message is received
    from the assembler completion queue. The consumer runs in a separate
    process; report tracker updates are performed via HTTP PUT to the
    orchestrator API.

    Expected payload format:
    {
        "message_id": str (optional),
        "timestamp": str (optional, ISO8601),
        "type": "draft_completed" (optional),
        "report_id": str (required),
        "workflow_id": str (optional),
        "status": "completed" | "failed" (required),
        "draft_url": str (optional),
        "error_message": str (optional, if status is "failed"),
        "app_data": object (optional – metadata to store on current step before accept)
    }

    Args:
        payload: Message payload dictionary
        message_id: SQS message ID

    Returns:
        True if processing was successful, False otherwise
    """
    try:
        report_id = payload.get("report_id")
        workflow_id = payload.get("workflow_id")
        status = payload.get("status", "unknown")
        draft_url = payload.get("draft_url")
        error_message = payload.get("error_message")
        app_data: Optional[Dict[str, Any]] = payload.get("app_data")

        logger.info(
            "Received assembler completion - report_id: %s, status: %s, message_id: %s",
            report_id,
            status,
            message_id
        )

        if not report_id:
            logger.error("Missing report_id in assembler completion message")
            return False

        if status == "completed":
            base_url = (settings.orchestrator_api_base_url or "").rstrip("/")
            if not base_url:
                logger.error("ORCHESTRATOR_API_BASE_URL is not configured")
                return False
            url = f"{base_url}/v1/report-tracker/{report_id}"
            body: Dict[str, Any] = {"action": "accept"}
            if app_data is not None:
                body["app_data"] = app_data
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.put(url, json=body)
            except httpx.HTTPError as e:
                logger.error(
                    "HTTP error calling report-tracker API for report_id %s: %s",
                    report_id,
                    str(e)
                )
                return False
            if response.status_code < 200 or response.status_code >= 300:
                logger.error(
                    "Report-tracker API returned %s for report_id %s: %s",
                    response.status_code,
                    report_id,
                    response.text[:500] if response.text else ""
                )
                return False
            messaging_service = get_messaging_service()
            messaging_service.notify_draft_completed(
                report_id=report_id,
                workflow_id=workflow_id,
                draft_url=draft_url
            )
            logger.info(
                "Draft completed notification sent to consumers - report_id: %s",
                report_id
            )

        elif status == "failed":
            logger.error(
                "Assembler reported failure for report_id: %s - Error: %s",
                report_id,
                error_message
            )
            # TODO: Implement error handling (retry, notify admin, etc.)

        else:
            logger.warning(
                "Unknown status '%s' in assembler completion for report_id: %s",
                status,
                report_id
            )

        return True

    except Exception as e:
        logger.error(
            "Error processing assembler completion message %s: %s",
            message_id,
            str(e)
        )
        return False


def start_assembler_completion_listener() -> None:
    """
    Start the background listener for assembler completion notifications.

    This should be called during application startup.
    """
    if not settings.messaging_enabled:
        logger.info("Messaging is disabled, skipping assembler completion listener")
        return

    logger.info("Starting assembler completion listener...")

    messaging_service = get_messaging_service()
    messaging_service.start_assembler_completion_listener(
        handler=handle_assembler_completion,
        continuous=True
    )


def stop_assembler_completion_listener() -> None:
    """
    Stop the background listener for assembler completion notifications.

    This should be called during application shutdown.
    """
    logger.info("Stopping assembler completion listener...")
    messaging_service = get_messaging_service()
    messaging_service.stop_assembler_completion_listener()
