"""
MessageConsumer - Utility class for consuming messages from AWS SQS.
This implementation follows the exact patterns from snssqs/consume_messages 4.py
"""
import json
import logging
import signal
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config.config import settings

logger = logging.getLogger(__name__)


class MessageConsumerError(Exception):
    """Base exception for MessageConsumer errors."""
    pass


class QueueNotFoundError(MessageConsumerError):
    """Exception raised when queue is not found."""
    pass


class MessageProcessingError(MessageConsumerError):
    """Exception raised when message processing fails."""
    pass


class MessageConsumer:
    """
    Consumer for SQS messages.

    This class provides methods to receive, process, and delete messages
    from AWS SQS queues. It supports both single-poll and continuous
    consumption modes.

    The consumer expects messages in the following formats:

    1. Direct SQS message:
       {
           "message_id": str,
           "timestamp": str,
           "type": str,
           "data": {...}
       }

    2. SNS notification (forwarded to SQS):
       {
           "Type": "Notification",
           "TopicArn": str,
           "Subject": str,
           "Message": "<JSON string of actual payload>",
           "Timestamp": str
       }

    Usage:
        consumer = MessageConsumer()

        # Define a message handler
        def my_handler(payload: Dict, message_id: str) -> bool:
            print(f"Processing: {payload}")
            return True  # Return True if processed successfully

        # Consume once
        consumer.consume_once(queue_name="my-queue", handler=my_handler)

        # Consume continuously
        consumer.consume_continuously(queue_name="my-queue", handler=my_handler)
    """

    def __init__(
        self,
        region: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None
    ) -> None:
        """
        Initialize the message consumer for AWS.

        Args:
            region: AWS region (defaults to settings.aws_region)
            aws_access_key_id: AWS access key (defaults to settings.aws_access_key_id)
            aws_secret_access_key: AWS secret key (defaults to settings.aws_secret_access_key)
            aws_session_token: AWS session token (defaults to settings.aws_session_token)
        """
        self.region = region or settings.aws_region
        self.aws_access_key_id = aws_access_key_id or settings.aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key or settings.aws_secret_access_key
        self.aws_session_token = aws_session_token or settings.aws_session_token

        # Consumer state
        self.running = True

        # Prepare client configuration
        self._client_config: Dict[str, Any] = {
            'region_name': self.region
        }

        # Add credentials if provided
        if self.aws_access_key_id and self.aws_secret_access_key:
            self._client_config['aws_access_key_id'] = self.aws_access_key_id
            self._client_config['aws_secret_access_key'] = self.aws_secret_access_key
            if self.aws_session_token:
                self._client_config['aws_session_token'] = self.aws_session_token

        # Initialize client (lazy initialization)
        self._sqs_client: Optional[Any] = None

        # Statistics tracking
        self.stats: Dict[str, int] = {
            'received': 0,
            'processed': 0,
            'failed': 0,
            'deleted': 0
        }

        # Queue URL cache
        self._queue_url_cache: Dict[str, str] = {}

        logger.info(
            "MessageConsumer initialized with region=%s",
            self.region
        )

    @property
    def sqs_client(self) -> Any:
        """Lazy initialization of SQS client."""
        if self._sqs_client is None:
            self._sqs_client = boto3.client('sqs', **self._client_config)
        return self._sqs_client

    def _get_queue_url(self, queue_name: str) -> str:
        """
        Get queue URL from queue name with caching.

        Args:
            queue_name: Name of the SQS queue

        Returns:
            Queue URL string

        Raises:
            QueueNotFoundError: If queue is not found
        """
        if queue_name in self._queue_url_cache:
            return self._queue_url_cache[queue_name]

        try:
            response = self.sqs_client.get_queue_url(QueueName=queue_name)
            queue_url = response['QueueUrl']
            self._queue_url_cache[queue_name] = queue_url
            return queue_url
        except ClientError as e:
            if e.response['Error']['Code'] == 'AWS.SimpleQueueService.NonExistentQueue':
                raise QueueNotFoundError(f"Queue '{queue_name}' not found") from e
            raise

    def _extract_payload(self, body_json: Any) -> Dict[str, Any]:
        """
        Extract the actual payload from message body.

        Handles both direct SQS messages and SNS notifications forwarded to SQS.

        SNS Notification format:
        {
            "Type": "Notification",
            "TopicArn": "arn:aws:sns:...",
            "Subject": "...",
            "Message": "<JSON string>",  # <-- The actual payload is here
            "Timestamp": "..."
        }

        Direct SQS format:
        {
            "message_id": "...",
            "timestamp": "...",
            "type": "...",
            "data": {...}
        }

        Args:
            body_json: Parsed JSON body from message

        Returns:
            Extracted payload dictionary
        """
        # Check if this is an SNS notification
        if isinstance(body_json, dict) and body_json.get('Type') == 'Notification':
            sns_message = body_json.get('Message', '{}')

            # If Message is already a dict, return it
            if isinstance(sns_message, dict):
                return sns_message

            # Parse the Message JSON string
            try:
                return json.loads(sns_message)
            except json.JSONDecodeError:
                return {'raw_message': sns_message}

        # Direct SQS message
        if isinstance(body_json, dict):
            return body_json

        return {'raw_body': body_json}

    def _extract_job_fields(self, payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        Extract job-related fields from payload.

        Expected payload structures:

        Structure 1 (nested tracker):
        {
            "tracker": {"report_id": str, "workflow_id": str},
            "create_data": {"content_product_name": str},
            "payload_id": str
        }

        Structure 2 (flat):
        {
            "report_id": str,
            "workflow_id": str,
            "cpm_id": str
        }

        Args:
            payload: Message payload dictionary

        Returns:
            Dictionary with extracted fields: report_id, workflow_id, cpm_id
        """
        tracker = payload.get('tracker') or {}
        create_data = payload.get('create_data') or {}

        report_id = tracker.get('report_id') or payload.get('report_id')
        workflow_id = (
            payload.get('payload_id') or
            payload.get('workflow_id') or
            tracker.get('workflow_id')
        )
        cpm_id = create_data.get('content_product_name') or payload.get('cpm_id')

        return {
            'report_id': report_id,
            'workflow_id': workflow_id,
            'cpm_id': cpm_id,
        }

    def receive_messages(
        self,
        queue_name: str,
        max_messages: Optional[int] = None,
        wait_time_seconds: Optional[int] = None,
        visibility_timeout: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Receive messages from SQS queue.

        Args:
            queue_name: Name of the SQS queue
            max_messages: Maximum number of messages to receive (1-10, defaults to settings)
            wait_time_seconds: Long polling wait time (defaults to settings)
            visibility_timeout: Visibility timeout for received messages (defaults to settings)

        Returns:
            List of message dictionaries from SQS
        """
        max_messages = max_messages or settings.sqs_max_messages
        wait_time_seconds = wait_time_seconds or settings.sqs_wait_time_seconds
        visibility_timeout = visibility_timeout or settings.sqs_visibility_timeout

        try:
            queue_url = self._get_queue_url(queue_name)

            response = self.sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=min(max_messages, 10),
                WaitTimeSeconds=wait_time_seconds,
                VisibilityTimeout=visibility_timeout,
                AttributeNames=['All'],
                MessageAttributeNames=['All']
            )

            messages = response.get('Messages', [])
            self.stats['received'] += len(messages)

            logger.debug(
                "Received %d messages from queue '%s'",
                len(messages),
                queue_name
            )

            return messages

        except QueueNotFoundError:
            logger.error("Queue '%s' not found", queue_name)
            return []
        except (BotoCoreError, ClientError) as e:
            logger.error(
                "Error receiving messages from queue '%s': %s",
                queue_name,
                str(e)
            )
            return []

    def process_message(
        self,
        message: Dict[str, Any],
        handler: Optional[Callable[[Dict[str, Any], str], bool]] = None
    ) -> bool:
        """
        Process a single message.

        Args:
            message: Raw SQS message dictionary containing:
                     - MessageId: str
                     - Body: str (JSON)
                     - ReceiptHandle: str
                     - MessageAttributes: dict (optional)
            handler: Optional callback function that receives (payload, message_id)
                    and returns True if processing successful

        Returns:
            True if processing successful, False otherwise
        """
        try:
            message_id = message.get('MessageId', 'unknown')
            body = message.get('Body', '{}')

            # Parse message body
            try:
                body_json = json.loads(body)
            except json.JSONDecodeError:
                body_json = {'raw_body': body}

            # Extract actual payload
            payload = self._extract_payload(body_json)

            # Log message details
            if isinstance(body_json, dict) and body_json.get('Type') == 'Notification':
                logger.info(
                    "Processing SNS Message (ID: %s) from topic: %s",
                    message_id,
                    body_json.get('TopicArn', 'unknown')
                )
            else:
                logger.info(
                    "Processing SQS Message (ID: %s)",
                    message_id
                )

            # Call handler if provided
            if handler:
                success = handler(payload, message_id)
                if success:
                    self.stats['processed'] += 1
                    return True
                else:
                    self.stats['failed'] += 1
                    return False

            # Default processing: extract job fields and log
            job_fields = self._extract_job_fields(payload)
            report_id = job_fields['report_id']
            workflow_id = job_fields['workflow_id']
            cpm_id = job_fields['cpm_id']

            if report_id and workflow_id:
                logger.info(
                    "Job fields extracted - report_id: %s, workflow_id: %s, cpm_id: %s",
                    report_id,
                    workflow_id,
                    cpm_id
                )
            else:
                logger.warning(
                    "Missing required fields - report_id: %s, workflow_id: %s",
                    report_id,
                    workflow_id
                )

            self.stats['processed'] += 1
            return True

        except Exception as e:
            logger.error("Error processing message: %s", str(e))
            self.stats['failed'] += 1
            return False

    def delete_message(self, queue_name: str, receipt_handle: str) -> bool:
        """
        Delete a message from the queue.

        Args:
            queue_name: Name of the SQS queue
            receipt_handle: Receipt handle of the message to delete

        Returns:
            True if deletion successful, False otherwise
        """
        try:
            queue_url = self._get_queue_url(queue_name)

            self.sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )

            self.stats['deleted'] += 1
            logger.debug("Message deleted from queue '%s'", queue_name)
            return True

        except (BotoCoreError, ClientError) as e:
            logger.error(
                "Error deleting message from queue '%s': %s",
                queue_name,
                str(e)
            )
            return False

    def consume_once(
        self,
        queue_name: str,
        handler: Optional[Callable[[Dict[str, Any], str], bool]] = None,
        auto_delete: Optional[bool] = None,
        max_messages: Optional[int] = None
    ) -> int:
        """
        Consume messages once (single poll).

        Args:
            queue_name: Name of the SQS queue
            handler: Optional callback function for processing messages
            auto_delete: Whether to automatically delete processed messages
            max_messages: Maximum number of messages to receive

        Returns:
            Number of messages processed successfully
        """
        auto_delete = auto_delete if auto_delete is not None else settings.sqs_auto_delete_messages

        logger.info("Polling queue once: %s", queue_name)

        messages = self.receive_messages(
            queue_name=queue_name,
            max_messages=max_messages,
            wait_time_seconds=settings.sqs_wait_time_seconds
        )

        processed_count = 0

        if messages:
            logger.info("Received %d message(s)", len(messages))

            for message in messages:
                success = self.process_message(message, handler)

                if success:
                    processed_count += 1
                    if auto_delete:
                        receipt_handle = message.get('ReceiptHandle')
                        if receipt_handle:
                            self.delete_message(queue_name, receipt_handle)
        else:
            logger.info("No messages available in queue")

        return processed_count

    def consume_continuously(
        self,
        queue_name: str,
        handler: Optional[Callable[[Dict[str, Any], str], bool]] = None,
        auto_delete: Optional[bool] = None,
        max_messages: Optional[int] = None,
        wait_time_seconds: Optional[int] = None,
        poll_interval: Optional[int] = None
    ) -> None:
        """
        Continuously consume messages from queue.

        This method runs in a loop until `self.running` is set to False
        or a keyboard interrupt is received.

        Args:
            queue_name: Name of the SQS queue
            handler: Optional callback function for processing messages
            auto_delete: Whether to automatically delete processed messages
            max_messages: Maximum number of messages to receive per poll
            wait_time_seconds: Long polling wait time
            poll_interval: Interval between polls (seconds) when not using long polling
        """
        auto_delete = auto_delete if auto_delete is not None else settings.sqs_auto_delete_messages
        wait_time_seconds = wait_time_seconds or settings.sqs_wait_time_seconds
        poll_interval = poll_interval or settings.sqs_poll_interval

        logger.info(
            "Starting continuous consumption from queue: %s (auto_delete=%s, wait_time=%ds)",
            queue_name,
            auto_delete,
            wait_time_seconds
        )

        while self.running:
            try:
                messages = self.receive_messages(
                    queue_name=queue_name,
                    max_messages=max_messages,
                    wait_time_seconds=wait_time_seconds
                )

                if messages:
                    logger.info(
                        "Received %d message(s) at %s",
                        len(messages),
                        datetime.now(timezone.utc).isoformat()
                    )

                    for message in messages:
                        success = self.process_message(message, handler)

                        if success and auto_delete:
                            receipt_handle = message.get('ReceiptHandle')
                            if receipt_handle:
                                if self.delete_message(queue_name, receipt_handle):
                                    logger.debug("Message deleted")
                        elif not auto_delete:
                            logger.debug("Message NOT deleted (auto_delete=False)")
                else:
                    logger.debug(
                        "No messages available (checked at %s)",
                        datetime.now(timezone.utc).strftime('%H:%M:%S')
                    )

                # Wait before next poll if not using long polling
                if wait_time_seconds == 0:
                    time.sleep(poll_interval)

            except KeyboardInterrupt:
                logger.info("Received interrupt signal, stopping...")
                self.running = False
                break
            except Exception as e:
                logger.error("Error in consumption loop: %s", str(e))
                time.sleep(poll_interval)

        logger.info("Consumer stopped")

    def stop(self) -> None:
        """Stop the continuous consumer."""
        self.running = False
        logger.info("Stop signal sent to consumer")

    def reset_stats(self) -> None:
        """Reset consumption statistics."""
        self.stats = {
            'received': 0,
            'processed': 0,
            'failed': 0,
            'deleted': 0
        }

    def get_stats(self) -> Dict[str, int]:
        """
        Get consumption statistics.

        Returns:
            Dictionary with keys: received, processed, failed, deleted
        """
        return self.stats.copy()

    def print_stats(self) -> None:
        """Print consumption statistics to logger."""
        logger.info("=" * 60)
        logger.info("CONSUMPTION STATISTICS")
        logger.info("=" * 60)
        logger.info("Messages received:  %d", self.stats['received'])
        logger.info("Messages processed: %d", self.stats['processed'])
        logger.info("Messages failed:    %d", self.stats['failed'])
        logger.info("Messages deleted:   %d", self.stats['deleted'])
        logger.info("=" * 60)


# Singleton instance for convenience
_consumer_instance: Optional[MessageConsumer] = None


def get_consumer() -> MessageConsumer:
    """
    Get the singleton MessageConsumer instance.

    Returns:
        MessageConsumer: The singleton consumer instance
    """
    global _consumer_instance
    if _consumer_instance is None:
        _consumer_instance = MessageConsumer()
    return _consumer_instance
