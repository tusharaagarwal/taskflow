"""
Assembler completion SQS consumer (in-process).

Consumes messages from the assembler-to-orchestrator queue, updates report tracker
in-process (no HTTP), and notifies consumers via SNS. All logic is self-contained; no
imports from app.services.aws.listeners or app.services.aws.consumer.
"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from app.config.config import settings
from app.db.database import AsyncSessionLocal
from app.exceptions import UnprocessableEntityException
from app.schemas.report_tracker import ReportTrackerUpdateRequest
from app.services.report_tracker_service import ReportTrackerService

logger = logging.getLogger(__name__)


def _extract_payload(body_json: Any) -> Dict[str, Any]:
    """
    Extract payload from SQS message body. Handles SNS-wrapped and direct SQS.

    - SNS-wrapped: body has Type=="Notification", payload is in Message (JSON string or dict).
    - Direct SQS: body is the payload dict.
    - Nested: if payload has a single key "data" or "body" that is a dict, unwrap once.
    """
    logger.debug(
        "Extracting payload from body; type=%s, has Type=%s",
        type(body_json).__name__,
        body_json.get("Type") if isinstance(body_json, dict) else None,
    )
    if isinstance(body_json, dict) and body_json.get("Type") == "Notification":
        sns_message = body_json.get("Message", "{}")
        if isinstance(sns_message, dict):
            out = sns_message
        else:
            try:
                out = json.loads(sns_message)
            except json.JSONDecodeError:
                logger.debug("Payload extraction fallback; returning raw_message/raw_body")
                return {"raw_message": sns_message}
        logger.debug(
            "Parsed SNS Message; keys=%s",
            list(out.keys()) if isinstance(out, dict) else "non-dict",
        )
        if isinstance(out, dict) and len(out) == 1:
            only_key = next(iter(out.keys()), None)
            if only_key in ("data", "body") and isinstance(out[only_key], dict):
                logger.debug("Unwrapping single key payload; key=%s", only_key)
                payload = out[only_key]
                logger.debug("Extracted payload keys: %s", list(payload.keys()))
                return payload
        payload = out if isinstance(out, dict) else {"raw_body": out}
        logger.debug("Extracted payload keys: %s", list(payload.keys()))
        return payload
    if isinstance(body_json, dict):
        if len(body_json) == 1 and next(iter(body_json.keys()), None) in ("data", "body"):
            inner = body_json.get("data") or body_json.get("body")
            if isinstance(inner, dict):
                logger.debug("Extracted payload keys: %s", list(inner.keys()))
                return inner
        logger.debug("Extracted payload keys: %s", list(body_json.keys()))
        return body_json
    logger.debug("Payload extraction fallback; returning raw_message/raw_body")
    payload = {"raw_body": body_json}
    logger.debug("Extracted payload keys: %s", list(payload.keys()))
    return payload


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

    logger.debug(
        "Notify consumers: report_id=%s, event_type=%s, pr_id=%s",
        report_id,
        event_type,
        pr_id,
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    message: Dict[str, Any] = {
        "message_id": f"msg_{timestamp}",
        "timestamp": timestamp,
        "type": "orchestrator",
        "queue_name": "orchestrator_to_workspace",
        "event_type": event_type,
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

        logger.debug(
            "Publishing to SNS topic (resolved or configured); topic_arn=%s",
            topic_arn,
        )
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


async def _handle_assembler_completion(payload: Dict[str, Any], message_id: str) -> bool:
    """
    Handle draft completion notification. Validate report_id; on status=completed
    update report-tracker in-process and notify consumers. No HTTP or base URL.

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
            update_data = ReportTrackerUpdateRequest(action="accept")
            try:
                async with AsyncSessionLocal() as db:
                    tracker = await ReportTrackerService.update(db, report_id, update_data)
            except (ValueError, UnprocessableEntityException) as e:
                logger.error(
                    "Report-tracker update failed for report_id %s: %s",
                    report_id,
                    str(e),
                )
                return False
            if not tracker:
                logger.error(
                    "Report-tracker not found for report_id %s",
                    report_id,
                )
                return False

            logger.info(
                "Report-tracker update succeeded in-process; report_id=%s",
                report_id,
            )
            logger.debug("Calling _notify_consumers for report_id=%s", report_id)
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
        self.queue_name: str = ""
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
            self.queue_name = queue_name
            logger.debug(
                "Using configured queue URL; region=%s, queue_name=%s",
                region,
                self.queue_name,
            )
            self.queue_url = queue_url_cfg
        else:
            self.queue_name = queue_name
            logger.debug(
                "Initializing SQS client; region=%s, queue_name=%s",
                region,
                queue_name,
            )
            response = self.sqs_client.get_queue_url(QueueName=queue_name)
            self.queue_url = response["QueueUrl"]
        logger.info(
            "SQS client initialized; queue_name=%s, queue_url=%s",
            self.queue_name,
            self.queue_url,
        )

    def _receive_messages_sync(self) -> Dict[str, Any]:
        max_messages = getattr(settings, "sqs_max_messages", 10)
        wait_time = getattr(settings, "sqs_wait_time_seconds", 20)
        visibility_timeout = getattr(settings, "sqs_visibility_timeout", 30)
        logger.debug(
            "Receiving messages; queue_name=%s, max=%s, wait_time=%s",
            self.queue_name,
            max_messages,
            wait_time,
        )
        response = self.sqs_client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=min(max_messages, 10),
            WaitTimeSeconds=wait_time,
            VisibilityTimeout=visibility_timeout,
            MessageAttributeNames=["All"],
        )
        messages = response.get("Messages", [])
        logger.debug(
            "Receive_message returned; queue_name=%s, message_count=%s",
            self.queue_name,
            len(messages),
        )
        return response

    async def _process_message(
        self, message_body: str, receipt_handle: str, message_id: str = "unknown"
    ) -> bool:
        logger.debug(
            "Processing message; queue_name=%s, message_id=%s, body_len=%s",
            self.queue_name,
            message_id,
            len(message_body),
        )
        try:
            try:
                body_json = json.loads(message_body)
                logger.debug(
                    "Body parsed as JSON; queue_name=%s, message_id=%s",
                    self.queue_name,
                    message_id,
                )
            except json.JSONDecodeError:
                body_json = {"raw_body": message_body}
                logger.debug(
                    "Body not valid JSON; using raw_body; queue_name=%s, message_id=%s",
                    self.queue_name,
                    message_id,
                )

            payload = _extract_payload(body_json)
            logger.debug(
                "Payload extracted; queue_name=%s, message_id=%s, payload_keys=%s",
                self.queue_name,
                message_id,
                list(payload.keys()),
            )
            success = await _handle_assembler_completion(payload, message_id)
            logger.debug(
                "Handler result; queue_name=%s, message_id=%s, success=%s",
                self.queue_name,
                message_id,
                success,
            )
            if not success:
                logger.warning(
                    "Message processing failed (handler returned False); queue_name=%s, message_id=%s, payload_keys=%s",
                    self.queue_name,
                    message_id,
                    list(payload.keys()),
                )

            if success:
                logger.debug(
                    "Deleting message from queue; queue_name=%s, message_id=%s",
                    self.queue_name,
                    message_id,
                )
                await self._delete_message(receipt_handle)
            return success

        except Exception as e:
            logger.error(
                "Error processing SQS message: %s",
                e,
                exc_info=True,
            )
            await self._delete_message(receipt_handle)
            return False

    async def _delete_message(self, receipt_handle: str) -> None:
        logger.debug(
            "Deleting SQS message; queue_name=%s, receipt_handle_prefix=%s",
            self.queue_name,
            receipt_handle[:24] if receipt_handle else "empty",
        )
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                lambda: self.sqs_client.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=receipt_handle,
                ),
            )
            logger.debug(
                "Deleted message from SQS; queue_name=%s, receipt_handle=%s...",
                self.queue_name,
                receipt_handle[:20],
            )
        except ClientError as e:
            logger.error("Failed to delete SQS message: %s", e)

    async def _consume_messages(self) -> None:
        logger.info(
            "Starting SQS consumer loop; queue_name=%s",
            self.queue_name,
        )

        while self.is_running:
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    self._executor,
                    self._receive_messages_sync,
                )

                messages = response.get("Messages", [])

                if not messages:
                    logger.debug(
                        "Poll returned no messages; queue_name=%s; continuing",
                        self.queue_name,
                    )
                    continue

                logger.info(
                    "Received %d messages from SQS; queue_name=%s",
                    len(messages),
                    self.queue_name,
                )

                tasks = []
                for message in messages:
                    message_body = message.get("Body", "{}")
                    receipt_handle = message.get("ReceiptHandle", "")
                    msg_id = message.get("MessageId", "unknown")
                    tasks.append(self._process_message(message_body, receipt_handle, msg_id))

                logger.debug(
                    "Dispatching %s message(s); queue_name=%s, message_ids=%s",
                    len(messages),
                    self.queue_name,
                    [m.get("MessageId") for m in messages],
                )
                results = await asyncio.gather(*tasks, return_exceptions=True)
                failed_pairs = [
                    (messages[i].get("MessageId", "unknown"), results[i])
                    for i in range(len(results))
                    if results[i] is False or isinstance(results[i], Exception)
                ]
                failed = len(failed_pairs)
                logger.debug(
                    "Batch processed; queue_name=%s, total=%s, success=%s, failed=%s",
                    self.queue_name,
                    len(messages),
                    len(messages) - failed,
                    failed,
                )
                if failed > 0:
                    failed_ids = [mid for mid, _ in failed_pairs]
                    logger.warning(
                        "Failed to process %d out of %d messages; queue_name=%s; failed_message_ids=%s",
                        failed,
                        len(messages),
                        self.queue_name,
                        failed_ids,
                    )
                    for msg_id, result in failed_pairs:
                        if isinstance(result, Exception):
                            logger.error(
                                "Exception while processing message_id=%s; queue_name=%s: %s",
                                msg_id,
                                self.queue_name,
                                result,
                                exc_info=(
                                    type(result),
                                    result,
                                    getattr(result, "__traceback__", None),
                                ),
                            )

            except ClientError as e:
                logger.error(
                    "AWS SQS client error; queue_name=%s: %s",
                    self.queue_name,
                    e,
                )
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(
                    "Unexpected error in SQS consumer; queue_name=%s: %s",
                    self.queue_name,
                    e,
                )
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
            logger.debug(
                "SQS consumer task created; queue_name=%s",
                self.queue_name,
            )
            logger.info(
                "SQS consumer started successfully; queue_name=%s",
                self.queue_name,
            )
        except Exception as e:
            logger.error("Failed to start SQS consumer: %s", e)
            self.is_running = False
            raise

    async def stop(self) -> None:
        if not self.is_running:
            return

        logger.info(
            "Stopping SQS consumer...; queue_name=%s",
            self.queue_name,
        )
        self.is_running = False

        if self._task:
            self._task.cancel()
            logger.debug(
                "Consumer task cancelled; queue_name=%s; waiting for shutdown",
                self.queue_name,
            )
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._executor.shutdown(wait=True)
        logger.info(
            "SQS consumer stopped; queue_name=%s",
            self.queue_name,
        )


sqs_consumer = AssemblerCompletionSQSConsumer()
