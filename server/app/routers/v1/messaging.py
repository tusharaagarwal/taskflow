"""
Messaging API endpoints for Workflow Orchestrator.

Publishing (SNS/SQS send) is done by this API. SQS consumption (assembler
completion) runs in a separate worker process (worker_sqs.py), not in-process.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from app.logger import logger
from app.services.messaging_manager import messaging_manager
from app.utils.security import sanitize_log_input
from app.config.config import settings

router = APIRouter()


@router.get("/messaging/status")
async def get_messaging_status():
    """Get the status of messaging services (publish-side and config).

    SQS consumption is handled by the standalone worker (worker_sqs.py);
    this endpoint reports API-side config and publish capability only.
    """
    try:
        if not settings.messaging_enabled:
            return {
                "status": "disabled",
                "message": "Messaging services are disabled in configuration",
                "sqs_worker_note": "SQS consumption runs in separate worker_sqs.py when messaging is enabled",
            }

        health_info = await messaging_manager.health_check()
        if isinstance(health_info, dict):
            health_info["sqs_worker_note"] = (
                "Assembler completion SQS consumption runs in separate worker (worker_sqs.py); "
                "scale workers independently of the API."
            )
        return health_info
        
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
        
        await messaging_manager.publish_report_update(
            report_id=report_id,
            update_type=update_type,
            data=data,
            subject=subject
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
