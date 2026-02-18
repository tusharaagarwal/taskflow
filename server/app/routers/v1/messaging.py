"""
Messaging API endpoints for Workflow Orchestrator.

Publishing (SNS/SQS send) is done by this API. SQS assembler completion
consumer runs in-process (app.services.sqs_consumer, started in lifespan).
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from app.logger import logger
from app.services.aws.messaging_service import get_messaging_service
from app.utils.security import sanitize_log_input
from app.config.config import settings

router = APIRouter()


@router.get("/messaging/status")
async def get_messaging_status():
    """Get the status of messaging services (publish-side and in-process SQS consumer).

    Assembler completion SQS consumer runs in-process (app.services.sqs_consumer).
    """
    try:
        if not settings.messaging_enabled:
            return {
                "status": "disabled",
                "message": "Messaging services are disabled in configuration",
                "sqs_consumer_note": "Assembler completion SQS consumer runs in-process when messaging is enabled",
            }

        return {
            "status": "healthy",
            "sqs_consumer": "in_process",
            "aws_connectivity": "connected",
            "config": {
                "region": getattr(settings, "aws_region", "ap-south-1"),
                "assembler_task_topic": getattr(settings, "assembler_task_topic_name", ""),
                "assembler_completion_queue": getattr(settings, "assembler_completion_queue_name", ""),
                "consumer_notification_topic": getattr(settings, "consumer_notification_topic_name", ""),
            },
            "sqs_consumer_note": (
                "Assembler completion SQS consumer runs in-process (app.services.sqs_consumer)."
            ),
        }
    except Exception as e:
        logger.error("Error getting messaging status: %s", sanitize_log_input(str(e)))
        raise HTTPException(status_code=500, detail="Failed to get messaging status")


@router.post("/messaging/publish-report-update")
async def publish_report_update(
    report_id: str,
    update_type: str,
    data: Dict[str, Any],
    subject: Optional[str] = None
):
    """Publish a report update to SNS topic"""
    try:
        if not settings.messaging_enabled:
            raise HTTPException(status_code=503, detail="Messaging services are disabled")

        messaging_service = get_messaging_service()
        status = data.get("status", "completed") if isinstance(data, dict) else "completed"
        messaging_service.notify_consumers(
            report_id=report_id,
            event_type=update_type,
            status=status,
            additional_data=data if isinstance(data, dict) else {"data": data},
        )

        return {
            "message": "Report update published successfully",
            "report_id": report_id,
            "update_type": update_type
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error publishing report update: %s", sanitize_log_input(str(e)))
        raise HTTPException(status_code=500, detail="Failed to publish report update")
