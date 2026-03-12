"""
Standalone script to consume from the consumer notification queue (orchestrator-to-workspace).

Uses the same async consumer pattern as the in-process sqs_consumer (worklist-style).
Messages are logged and then deleted. No import from app.services.aws.consumer.

Usage (from workflow_orchestrator/server):
  poetry run python scripts/run_consumer_notification_consumer.py

Requires:
  - AWS credentials
  - Queue name from config: consumer_notification_queue_name (default orchestrator-to-workspace)
"""
import asyncio
import json
import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict

# Ensure server root is on path so "app" resolves
_server_root = Path(__file__).resolve().parent.parent
if str(_server_root) not in sys.path:
    sys.path.insert(0, str(_server_root))


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)

_is_running = True


def _extract_payload(body_json: Any) -> Dict[str, Any]:
    """Extract payload from SQS body (SNS-wrapped or direct)."""
    if isinstance(body_json, dict) and body_json.get("Type") == "Notification":
        sns_message = body_json.get("Message", "{}")
        if isinstance(sns_message, dict):
            return sns_message
        try:
            return json.loads(sns_message)
        except json.JSONDecodeError:
            return {"raw_message": sns_message}
    if isinstance(body_json, dict):
        return body_json
    return {"raw_body": body_json}


def _handle_consumer_notification(payload: Dict[str, Any], message_id: str) -> bool:
    """Log the notification payload and return True so the message is deleted."""
    report_id = payload.get("report_id", "")
    event_type = payload.get("event_type") or payload.get("type", "")
    status = payload.get("status", "")
    pr_id = payload.get("pr_id", "")
    transaction_id = payload.get("transaction_id", "")
    logger.info(
        "Consumer notification - report_id: %s, pr_id: %s, transaction_id: %s, type: %s, status: %s, message_id: %s",
        report_id,
        pr_id,
        transaction_id,
        event_type,
        status,
        message_id,
    )
    logger.debug("Full payload: %s", json.dumps(payload, default=str)[:500])
    return True


async def _run_consumer() -> None:
    import boto3
    from botocore.exceptions import ClientError

    from app.config.config import settings

    if not settings.messaging_enabled:
        logger.warning("Messaging is disabled. Set messaging_enabled in config.")
        return

    queue_name = getattr(settings, "consumer_notification_queue_name", "orchestrator-to-workspace")
    queue_url_cfg = (getattr(settings, "consumer_notification_queue_url", None) or "").strip()
    region = getattr(settings, "aws_region", "ap-south-1")

    client_kwargs: Dict[str, Any] = {"service_name": "sqs", "region_name": region}
    if getattr(settings, "aws_access_key_id", None) and getattr(settings, "aws_secret_access_key", None):
        client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        if getattr(settings, "aws_session_token", None):
            client_kwargs["aws_session_token"] = settings.aws_session_token

    sqs = boto3.client(**client_kwargs)
    if queue_url_cfg:
        queue_url = queue_url_cfg
    else:
        resp = sqs.get_queue_url(QueueName=queue_name)
        queue_url = resp["QueueUrl"]

    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="consumer-notif")

    def receive() -> Any:
        return sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            MessageAttributeNames=["All"],
        )

    logger.info("Starting consumer notification consumer (queue: %s). Ctrl+C to stop.", queue_name)

    while _is_running:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(executor, receive)
            messages = response.get("Messages", [])

            if not messages:
                continue

            for msg in messages:
                body = msg.get("Body", "{}")
                receipt = msg.get("ReceiptHandle", "")
                msg_id = msg.get("MessageId", "unknown")
                try:
                    body_json = json.loads(body)
                except json.JSONDecodeError:
                    body_json = {"raw_body": body}
                payload = _extract_payload(body_json)
                if _handle_consumer_notification(payload, msg_id):
                    await loop.run_in_executor(
                        executor,
                        lambda r=receipt: sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=r),
                    )

        except ClientError as e:
            logger.error("AWS SQS error: %s", e)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break

    executor.shutdown(wait=True)
    logger.info("Consumer exited.")


def main() -> None:
    global _is_running
    _configure_logging()

    def _shutdown(*_args: object) -> None:
        global _is_running
        logger.info("Shutdown requested (Ctrl+C or SIGTERM)...")
        _is_running = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        asyncio.run(_run_consumer())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
