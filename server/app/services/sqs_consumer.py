"""
Assembler completion SQS consumer (in-process).

Consumes messages from the assembler-to-orchestrator queue, updates report tracker
via HTTP PUT, and notifies consumers via SNS. All logic is self-contained; no
imports from app.services.aws.listeners or app.services.aws.consumer.
"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
import httpx
from botocore.exceptions import ClientError

from app.config.config import settings

logger = logging.getLogger(__name__)


def _extract_payload(body_json: Any) -> Dict[str, Any]:
    """
    Extract payload from SQS message body. Handles SNS-wrapped and direct SQS.

    - SNS-wrapped: body has Type=="Notification", payload is in Message (JSON string or dict).
    - Direct SQS: body is the payload dict.
    - Nested: if payload has a single key "data" or "body" that is a dict, unwrap once.
    """
    if isinstance(body_json, dict) and body_json.get("Type") == "Notification":
        sns_message = body_json.get("Message", "{}")
        if isinstance(sns_message, dict):
            out = sns_message
        else:
            try:
                out = json.loads(sns_message)
            except json.JSONDecodeError:
                return {"raw_message": sns_message}
        if isinstance(out, dict) and len(out) == 1:
            only_key = next(iter(out.keys()), None)
            if only_key in ("data", "body") and isinstance(out[only_key], dict):
                return out[only_key]
        return out if isinstance(out, dict) else {"raw_body": out}
    if isinstance(body_json, dict):
        if len(body_json) == 1 and next(iter(body_json.keys()), None) in ("data", "body"):
            inner = body_json.get("data") or body_json.get("body")
            if isinstance(inner, dict):
                return inner
        return body_json
    return {"raw_body": body_json}


def _notify_consumers(
    report_id: str,
    event_type: str,
    pr_id: Optional[str] = None,
    transaction_id: Optional[str] = None,
    status: str = "completed",
) -> None:
    """
    Notify consumer applications (SNS publish). Implemented inline; no aws/messaging_service.
    """
    if not getattr(settings, "messaging_enabled", True):
        logger.debug("Messaging disabled, skipping notify_consumers")
        return

    timestamp = datetime.now(timezone.utc).isoformat()
    message: Dict[str, Any] = {
        "message_id": f"msg_{timestamp}",
        "timestamp": timestamp,
        "type": event_type,
        "report_id": report_id,
        "status": status,
    }
    if pr_id is not None:
        message["pr_id"] = pr_id
    if transaction_id is not None:
        message["transaction_id"] = transaction_id

    topic_name = getattr(settings, "consumer_notification_topic_name", "orchestrator-to-workspace")
    message_group_id = getattr(
        settings, "consumer_notification_message_group_id", "consumer-notification-group-1"
    )
    region = getattr(settings, "aws_region", "ap-south-1")

    client_kwargs: Dict[str, Any] = {"region_name": region}
    if getattr(settings, "aws_access_key_id", None) and getattr(settings, "aws_secret_access_key", None):
        client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        if getattr(settings, "aws_session_token", None):
            client_kwargs["aws_session_token"] = settings.aws_session_token

    try:
        sns = boto3.client("sns", **client_kwargs)
        if topic_name.startswith("arn:"):
            topic_arn = topic_name
        else:
            sts = boto3.client("sts", **client_kwargs)
            account_id = sts.get_caller_identity()["Account"]
            topic_arn = f"arn:aws:sns:{region}:{account_id}:{topic_name}"

        message_json = json.dumps(message)
        publish_params: Dict[str, Any] = {
            "TopicArn": topic_arn,
            "Message": message_json,
            "Subject": f"report_update_{event_type}",
        }
        if topic_name.endswith(".fifo"):
            dedup_id = f"consumer-{report_id}-{event_type}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            publish_params["MessageGroupId"] = message_group_id
            publish_params["MessageDeduplicationId"] = dedup_id

        sns.publish(**publish_params)
        logger.info(
            "Published consumer notification to SNS - report_id: %s, event: %s",
            report_id,
            event_type,
        )
    except Exception as e:
        logger.error("Failed to publish consumer notification to SNS: %s", e)


def _handle_assembler_completion(payload: Dict[str, Any], message_id: str) -> bool:
    """
    Handle draft completion notification. Validate report_id; on status=completed
    PUT report-tracker and notify consumers. All logic inline; no aws/listeners.

    Expected payload: report_id (or reportId), status, optional pr_id, transaction_id,
    step_name, content_type, completed_date. See MESSAGING_CLEANUP_LOG.md.
    """
    try:
        report_id = payload.get("report_id") or payload.get("reportId")
        if isinstance(report_id, str):
            report_id = report_id.strip() or None
        status = payload.get("status", "unknown")
        step_name = payload.get("step_name")
        pr_id = payload.get("pr_id") or payload.get("prId")
        transaction_id = payload.get("transaction_id") or payload.get("transactionId")

        logger.info(
            "Received assembler completion - report_id: %s, status: %s, step_name: %s, pr_id: %s, message_id: %s",
            report_id,
            status,
            step_name,
            pr_id,
            message_id,
        )

        if not report_id:
            logger.error(
                "Missing report_id in assembler completion message; payload top-level keys: %s",
                list(payload.keys()),
            )
            return False

        if status == "completed":
            base_url = (getattr(settings, "orchestrator_api_base_url", None) or "").rstrip("/")
            if not base_url:
                logger.error("ORCHESTRATOR_API_BASE_URL is not configured")
                return False
            url = f"{base_url}/v1/report-tracker/{report_id}"
            body: Dict[str, Any] = {"action": "accept"}
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.put(url, json=body)
            except httpx.HTTPError as e:
                logger.error(
                    "HTTP error calling report-tracker API for report_id %s: %s",
                    report_id,
                    str(e),
                )
                return False
            if response.status_code < 200 or response.status_code >= 300:
                logger.error(
                    "Report-tracker API returned %s for report_id %s: %s",
                    response.status_code,
                    report_id,
                    response.text[:500] if response.text else "",
                )
                return False

            _notify_consumers(
                report_id=report_id,
                event_type="draft_completed",
                pr_id=pr_id,
                transaction_id=transaction_id,
                status="completed",
            )
            logger.info("Draft completed notification sent to consumers - report_id: %s", report_id)

        elif status == "failed":
            logger.error("Assembler reported failure for report_id: %s", report_id)

        else:
            logger.warning(
                "Unknown status '%s' in assembler completion for report_id: %s",
                status,
                report_id,
            )

        return True

    except Exception as e:
        logger.error(
            "Error processing assembler completion message %s: %s",
            message_id,
            str(e),
        )
        return False


class AssemblerCompletionSQSConsumer:
    """In-process SQS consumer for assembler completion queue (worklist-style)."""

    def __init__(self) -> None:
        self.sqs_client: Any = None
        self.queue_url: Optional[str] = None
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="sqs-consumer")

    def _initialize_sqs_client(self) -> None:
        if not getattr(settings, "messaging_enabled", True):
            raise ValueError("Messaging is disabled")

        region = getattr(settings, "aws_region", "ap-south-1")
        queue_url_cfg = (getattr(settings, "assembler_completion_queue_url", None) or "").strip()
        queue_name = getattr(settings, "assembler_completion_queue_name", "assembler-to-orchestrator")

        client_kwargs: Dict[str, Any] = {"service_name": "sqs", "region_name": region}
        if getattr(settings, "aws_access_key_id", None) and getattr(settings, "aws_secret_access_key", None):
            client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            if getattr(settings, "aws_session_token", None):
                client_kwargs["aws_session_token"] = settings.aws_session_token

        self.sqs_client = boto3.client(**client_kwargs)
        if queue_url_cfg:
            self.queue_url = queue_url_cfg
        else:
            response = self.sqs_client.get_queue_url(QueueName=queue_name)
            self.queue_url = response["QueueUrl"]
        logger.info("SQS client initialized for queue: %s", self.queue_url)

    def _receive_messages_sync(self) -> Dict[str, Any]:
        max_messages = getattr(settings, "sqs_max_messages", 10)
        wait_time = getattr(settings, "sqs_wait_time_seconds", 20)
        visibility_timeout = getattr(settings, "sqs_visibility_timeout", 30)
        return self.sqs_client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=min(max_messages, 10),
            WaitTimeSeconds=wait_time,
            VisibilityTimeout=visibility_timeout,
            MessageAttributeNames=["All"],
        )

    async def _process_message(
        self, message_body: str, receipt_handle: str, message_id: str = "unknown"
    ) -> bool:
        try:
            try:
                body_json = json.loads(message_body)
            except json.JSONDecodeError:
                body_json = {"raw_body": message_body}

            payload = _extract_payload(body_json)
            success = _handle_assembler_completion(payload, message_id)

            if success:
                await self._delete_message(receipt_handle)
            return success

        except Exception as e:
            logger.error("Error processing SQS message: %s", e)
            await self._delete_message(receipt_handle)
            return False

    async def _delete_message(self, receipt_handle: str) -> None:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                lambda: self.sqs_client.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=receipt_handle,
                ),
            )
            logger.debug("Deleted message from SQS: %s...", receipt_handle[:20])
        except ClientError as e:
            logger.error("Failed to delete SQS message: %s", e)

    async def _consume_messages(self) -> None:
        logger.info("Starting SQS consumer loop")

        while self.is_running:
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    self._executor,
                    self._receive_messages_sync,
                )

                messages = response.get("Messages", [])

                if not messages:
                    continue

                logger.info("Received %d messages from SQS", len(messages))

                tasks = []
                for message in messages:
                    message_body = message.get("Body", "{}")
                    receipt_handle = message.get("ReceiptHandle", "")
                    msg_id = message.get("MessageId", "unknown")
                    tasks.append(self._process_message(message_body, receipt_handle, msg_id))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                failed = sum(1 for r in results if r is False or isinstance(r, Exception))
                if failed > 0:
                    logger.warning("Failed to process %d out of %d messages", failed, len(messages))

            except ClientError as e:
                logger.error("AWS SQS client error: %s", e)
                await asyncio.sleep(5)
            except Exception as e:
                logger.error("Unexpected error in SQS consumer: %s", e)
                await asyncio.sleep(5)

    async def start(self) -> None:
        if self.is_running:
            logger.warning("SQS consumer is already running")
            return

        if not getattr(settings, "messaging_enabled", True):
            logger.info("Messaging is disabled, skipping SQS consumer")
            return

        try:
            self._initialize_sqs_client()
            self.is_running = True
            self._task = asyncio.create_task(self._consume_messages())
            logger.info("SQS consumer started successfully")
        except Exception as e:
            logger.error("Failed to start SQS consumer: %s", e)
            self.is_running = False
            raise

    async def stop(self) -> None:
        if not self.is_running:
            return

        logger.info("Stopping SQS consumer...")
        self.is_running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._executor.shutdown(wait=True)
        logger.info("SQS consumer stopped")


sqs_consumer = AssemblerCompletionSQSConsumer()
