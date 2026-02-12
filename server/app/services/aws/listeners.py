"""
Listeners for incoming AWS SQS messages.
This module provides background listeners for:
- Content Assembler completion notifications
"""
import logging
from typing import Any, Dict
from app.config.config import settings
from app.services.aws.messaging_service import get_messaging_service

logger = logging.getLogger(__name__)


def handle_assembler_completion(payload: Dict[str, Any], message_id: str) -> bool:
    """
    Handle draft completion notification from Content Assembler.

    This function is called by the consumer when a message is received
    from the assembler completion queue.

    Expected payload format:
    {
        "message_id": str,
        "timestamp": str,
        "type": "draft_completed",
        "report_id": str,
        "workflow_id": str,
        "status": "completed" | "failed",
        "draft_url": str (optional),
        "error_message": str (optional, if status is "failed")
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
            # Notify consuming applications that draft is ready
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
