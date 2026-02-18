"""
MessagingService - High-level service for Workflow Orchestrator messaging flows.
This module provides:
1. notify_assembler_to_start() - Tell Content Assembler to pick up a task
2. Assembler completion is handled by app.services.sqs_consumer (in-process, FastAPI lifespan)
3. notify_consumers() - Notify consumer applications about report updates (any event type)
"""
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from app.config.config import settings
from app.services.aws.publisher import MessagePublisher, get_publisher
from app.services.aws.consumer import MessageConsumer, get_consumer

logger = logging.getLogger(__name__)


class MessagingServiceError(Exception):
    """Base exception for MessagingService errors."""
    pass


class MessagingService:
    """
    High-level messaging service for Workflow Orchestrator.

    Provides convenience methods for the three main messaging flows:
    1. Orchestrator → Content Assembler (notify to start draft)
    2. Content Assembler → Orchestrator (draft completed)
    3. Orchestrator → Consuming Applications (notify consumers)
    """

    def __init__(
        self,
        publisher: Optional[MessagePublisher] = None,
        consumer: Optional[MessageConsumer] = None
    ) -> None:
        """
        Initialize the messaging service.

        Args:
            publisher: Optional MessagePublisher instance (uses singleton if not provided)
            consumer: Optional MessageConsumer instance (uses singleton if not provided)
        """
        self._publisher = publisher
        self._consumer = consumer
        logger.info("MessagingService initialized")

    @property
    def publisher(self) -> MessagePublisher:
        """Get or create the MessagePublisher instance."""
        if self._publisher is None:
            self._publisher = get_publisher()
        return self._publisher

    @property
    def consumer(self) -> MessageConsumer:
        """Get or create the MessageConsumer instance."""
        if self._consumer is None:
            self._consumer = get_consumer()
        return self._consumer

    # ================================================================
    # FLOW 1: Orchestrator → Content Assembler (Notify to Start)
    # ================================================================

    def notify_assembler_to_start(
        self,
        report_id: str,
        workflow_id: str,
        cpm_id: Optional[str] = None,
        pr_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        action_code: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        publish_to_sns: bool = True,
        send_to_sqs: bool = True
    ) -> Dict[str, Any]:
        """
        Notify Content Assembler to start creating the first draft of the report.

        This is called after creating a report tracker. The message is sent to:
        - SNS Topic: For broadcasting (if publish_to_sns=True)
        - SQS Queue: For direct consumption by assembler (if send_to_sqs=True)

        Message Format (flat structure):
        {
            "message_id": "msg_<timestamp>",
            "timestamp": "<ISO8601>",
            "type": "assembler_task",
            "report_id": "<report_id>",
            "workflow_id": "<workflow_id>",
            "content_product_name": "<cpm_id>",
            "payload_id": "<workflow_id>",
            "pr_id": "<pr_id>",
            "transaction_id": "<transaction_id>",
            "action_code": "<action_code>"
        }

        Args:
            report_id: Unique identifier for the report
            workflow_id: Workflow identifier (also used as payload_id)
            cpm_id: Content Product Manager ID
            pr_id: PR identifier
            transaction_id: Transaction identifier
            action_code: Action code for the workflow
            additional_data: Optional extra data to include in message
            publish_to_sns: Whether to publish to SNS topic (default: True)
            send_to_sqs: Whether to send to SQS queue (default: True)

        Returns:
            Dictionary with 'sns_response' and/or 'sqs_response' keys

        Raises:
            MessagingServiceError: If messaging is disabled or both targets are skipped
        """
        if not settings.messaging_enabled:
            logger.warning("Messaging is disabled, skipping notify_assembler_to_start")
            return {"status": "skipped", "reason": "messaging_disabled"}

        if not publish_to_sns and not send_to_sqs:
            raise MessagingServiceError(
                "At least one of publish_to_sns or send_to_sqs must be True"
            )

        timestamp = datetime.now(timezone.utc).isoformat()

        # Construct message (flat structure)
        message: Dict[str, Any] = {
            "message_id": f"msg_{timestamp}",
            "timestamp": timestamp,
            "type": "assembler_task",
            "report_id": report_id,
            "workflow_id": workflow_id,
            "content_product_name": cpm_id or "",
            "payload_id": workflow_id
        }

        # Add optional fields
        if pr_id:
            message["pr_id"] = pr_id
        if transaction_id:
            message["transaction_id"] = transaction_id
        if action_code:
            message["action_code"] = action_code
        if additional_data:
            message.update(additional_data)

        # Generate deduplication ID for FIFO
        dedup_id = f"{report_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        result: Dict[str, Any] = {}

        # Publish to SNS
        if publish_to_sns:
            try:
                sns_response = self.publisher.publish_to_sns(
                    topic_name=settings.assembler_task_topic_name,
                    message=message,
                    subject="orchestrator-to-assembler_task",
                    message_group_id=settings.assembler_message_group_id,
                    message_deduplication_id=dedup_id
                )
                result["sns_response"] = sns_response
                logger.info(
                    "Published assembler task to SNS - report_id: %s, MessageId: %s",
                    report_id,
                    sns_response.get("MessageId", "unknown")
                )
            except Exception as e:
                logger.error("Failed to publish to SNS: %s", str(e))
                result["sns_error"] = str(e)

        # Send to SQS
        if send_to_sqs:
            try:
                sqs_response = self.publisher.send_to_sqs(
                    queue_name=settings.assembler_task_queue_name,
                    message=message,
                    message_group_id=settings.assembler_message_group_id,
                    message_deduplication_id=f"{dedup_id}-sqs"
                )
                result["sqs_response"] = sqs_response
                logger.info(
                    "Sent assembler task to SQS - report_id: %s, MessageId: %s",
                    report_id,
                    sqs_response.get("MessageId", "unknown")
                )
            except Exception as e:
                logger.error("Failed to send to SQS: %s", str(e))
                result["sqs_error"] = str(e)

        return result

    # ================================================================
    # FLOW 2: Content Assembler → Orchestrator (Draft Completed)
    # ================================================================

    def start_assembler_completion_listener(
        self,
        handler: Callable[[Dict[str, Any], str], bool],
        continuous: bool = True
    ) -> None:
        """
        No-op. Assembler completion is handled by app.services.sqs_consumer
        (started in app.main lifespan). Start the API to consume messages.
        Start listening for draft completion notifications from Content Assembler.

        The handler receives the payload and message_id, and should return True
        if processing was successful (message will be deleted), False otherwise.

        Expected incoming message format (assembler → orchestrator):
        {
            "report_id": str (required),
            "pr_id": str,
            "transaction_id": str,
            "content_type": str,
            "step_name": str (e.g. "assembled_draft"),
            "status": "completed" | "failed" (required),
            "completed_date": str (e.g. ISO8601)
        }

        Args:
            handler: Callback function (payload, message_id) -> bool
            continuous: If True, listen continuously; if False, poll once
        """
        if not settings.messaging_enabled:
            logger.warning("Messaging is disabled, skipping assembler completion listener")
            return

        logger.info(
            "Assembler completion is handled by app.services.sqs_consumer (in-process). "
            "Start the API (e.g. uvicorn app.main:app) to run the consumer."
        )

    def stop_assembler_completion_listener(self) -> None:
        """No-op. Assembler completion consumer is stopped with the API (app.main lifespan)."""
        logger.info("Assembler completion consumer is stopped with the API process.")

    # ================================================================
    # FLOW 3: Orchestrator → Consuming Applications (Notify Consumers)
    # ================================================================

    def notify_consumers(
        self,
        report_id: str,
        event_type: str,
        pr_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        status: str = "completed",
        additional_data: Optional[Dict[str, Any]] = None,
        publish_to_sns: bool = True,
        send_to_sqs: bool = False
    ) -> Dict[str, Any]:
        """
        Notify consumer applications about a report update.

        Use this for any event that consumer apps need to know about:
        draft completed, report published, status changes, etc. Identifiers
        are report_id plus optional pr_id and transaction_id.

        Message format:
        {
            "message_id": "msg_<timestamp>",
            "timestamp": "<ISO8601>",
            "type": "<event_type>",
            "report_id": "<report_id>",
            "pr_id": "<pr_id>",           // when provided
            "transaction_id": "<transaction_id>",  // when provided
            "status": "<status>",
            "data": {...}                  // optional extra payload from additional_data
        }

        Args:
            report_id: Report identifier (required).
            event_type: Event type (e.g. "draft_completed", "report_published").
            pr_id: Optional PR identifier.
            transaction_id: Optional transaction identifier.
            status: Status of the event (default "completed").
            additional_data: Optional extra payload for consumers (stored in message["data"]).
            publish_to_sns: Whether to publish to SNS (default True).
            send_to_sqs: Whether to send to SQS (default False).

        Returns:
            Dictionary with response information.
        """
        if not settings.messaging_enabled:
            logger.warning("Messaging is disabled, skipping notify_consumers")
            return {"status": "skipped", "reason": "messaging_disabled"}

        timestamp = datetime.now(timezone.utc).isoformat()

        message: Dict[str, Any] = {
            "message_id": f"msg_{timestamp}",
            "timestamp": timestamp,
            "type": event_type,
            "report_id": report_id,
            "status": status
        }
        if pr_id is not None:
            message["pr_id"] = pr_id
        if transaction_id is not None:
            message["transaction_id"] = transaction_id
        if additional_data:
            message["data"] = dict(additional_data)

        # Generate deduplication ID for FIFO
        dedup_id = f"consumer-{report_id}-{event_type}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        result: Dict[str, Any] = {}

        # Publish to SNS (primary for fan-out to multiple consumers)
        if publish_to_sns:
            try:
                sns_response = self.publisher.publish_to_sns(
                    topic_name=settings.consumer_notification_topic_name,
                    message=message,
                    subject=f"report_update_{event_type}",
                    message_group_id=settings.consumer_notification_message_group_id,
                    message_deduplication_id=dedup_id
                )
                result["sns_response"] = sns_response
                logger.info(
                    "Published consumer notification to SNS - report_id: %s, event: %s",
                    report_id,
                    event_type
                )
            except Exception as e:
                logger.error("Failed to publish consumer notification to SNS: %s", str(e))
                result["sns_error"] = str(e)

        # Send to SQS (optional, for single consumer or backup)
        if send_to_sqs:
            try:
                sqs_response = self.publisher.send_to_sqs(
                    queue_name=settings.consumer_notification_queue_name,
                    message=message,
                    message_group_id=settings.consumer_notification_message_group_id,
                    message_deduplication_id=f"{dedup_id}-sqs"
                )
                result["sqs_response"] = sqs_response
                logger.info(
                    "Sent consumer notification to SQS - report_id: %s, event: %s",
                    report_id,
                    event_type
                )
            except Exception as e:
                logger.error("Failed to send consumer notification to SQS: %s", str(e))
                result["sqs_error"] = str(e)

        return result


# Singleton instance
_messaging_service_instance: Optional[MessagingService] = None


def get_messaging_service() -> MessagingService:
    """
    Get the singleton MessagingService instance.

    Returns:
        MessagingService: The singleton instance
    """
    global _messaging_service_instance
    if _messaging_service_instance is None:
        _messaging_service_instance = MessagingService()
    return _messaging_service_instance
