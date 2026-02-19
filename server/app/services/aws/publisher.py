"""
MessagePublisher - Utility class for publishing messages to AWS SNS and SQS.
This implementation follows the exact patterns from snssqs/publish_messages 3.py
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config.config import settings

logger = logging.getLogger(__name__)


class MessagePublisherError(Exception):
    """Base exception for MessagePublisher errors."""
    pass


class SNSPublishError(MessagePublisherError):
    """Exception raised when SNS publish fails."""
    pass


class SQSPublishError(MessagePublisherError):
    """Exception raised when SQS send fails."""
    pass


class MessagePublisher:
    """
    Publisher for SNS and SQS messages.

    This class provides methods to publish JSON messages to AWS SNS topics
    and SQS queues. It supports both standard and FIFO topics/queues.

    Usage:
        publisher = MessagePublisher()

        # Publish to SNS
        response = publisher.publish_to_sns(
            topic_name="my-topic.fifo",
            message={"event": "workflow_completed", "id": "123"},
            message_group_id="workflow-group"
        )

        # Send to SQS
        response = publisher.send_to_sqs(
            queue_name="my-queue",
            message={"task": "process", "data": {...}}
        )
    """

    def __init__(
        self,
        region: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None
    ) -> None:
        """
        Initialize the message publisher for AWS.

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

        # Initialize clients (lazy initialization for better error handling)
        self._sns_client: Optional[Any] = None
        self._sqs_client: Optional[Any] = None
        self._sts_client: Optional[Any] = None
        self._account_id: Optional[str] = None

        logger.info(
            "MessagePublisher initialized with region=%s",
            self.region
        )

    @property
    def sns_client(self) -> Any:
        """Lazy initialization of SNS client."""
        if self._sns_client is None:
            self._sns_client = boto3.client('sns', **self._client_config)
        return self._sns_client

    @property
    def sqs_client(self) -> Any:
        """Lazy initialization of SQS client."""
        if self._sqs_client is None:
            self._sqs_client = boto3.client('sqs', **self._client_config)
        return self._sqs_client

    @property
    def account_id(self) -> str:
        """Get AWS account ID for ARN construction."""
        if self._account_id is None:
            if self._sts_client is None:
                self._sts_client = boto3.client('sts', **self._client_config)
            self._account_id = self._sts_client.get_caller_identity()['Account']
        return self._account_id

    def _format_message_attributes(
        self,
        attributes: Dict[str, Any]
    ) -> Dict[str, Dict[str, str]]:
        """
        Format message attributes for SNS/SQS.

        Args:
            attributes: Dictionary of attributes to format

        Returns:
            Formatted attributes dictionary compatible with AWS SDK
        """
        formatted: Dict[str, Dict[str, str]] = {}
        for key, value in attributes.items():
            if isinstance(value, str):
                formatted[key] = {'DataType': 'String', 'StringValue': value}
            elif isinstance(value, (int, float)):
                formatted[key] = {'DataType': 'Number', 'StringValue': str(value)}
            else:
                formatted[key] = {'DataType': 'String', 'StringValue': json.dumps(value)}
        return formatted

    def _construct_topic_arn(self, topic_name: str) -> str:
        """
        Construct full ARN for SNS topic.

        Args:
            topic_name: Name of the SNS topic or full ARN

        Returns:
            Full ARN string for the topic
        """
        if topic_name.startswith('arn:'):
            return topic_name
        return f"arn:aws:sns:{self.region}:{self.account_id}:{topic_name}"

    def _generate_deduplication_id(self, sequence: int = 0) -> str:
        """
        Generate a unique deduplication ID for FIFO topics/queues.

        Args:
            sequence: Optional sequence number for uniqueness

        Returns:
            Unique deduplication ID string
        """
        timestamp = datetime.now(timezone.utc).timestamp()
        return f"msg-{timestamp}-{sequence}"

    def publish_to_sns(
        self,
        topic_name: str,
        message: Dict[str, Any],
        subject: Optional[str] = None,
        message_attributes: Optional[Dict[str, Any]] = None,
        message_group_id: Optional[str] = None,
        message_deduplication_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Publish a JSON message to SNS topic.

        The message format published will be:
        {
            "message_id": "msg_<timestamp>",
            "timestamp": "<ISO8601 timestamp>",
            "type": "<from message or 'default'>",
            "data": {
                "pr_id": "<report_id>",
                "content": "<message content>",
                "priority": "<priority level>"
            }
        }

        Args:
            topic_name: Name of the SNS topic (or full ARN)
            message: JSON message dictionary to publish. Should contain:
                     - For workflow events: {"pr_id": str, "content": str, "priority": str}
                     - For assembly events: {"assembly_id": str, "event_type": str, "data": dict}
            subject: Optional message subject (default: 'workflow_task')
            message_attributes: Optional message attributes dictionary
            message_group_id: Required for FIFO topics (defaults to settings.sns_default_message_group_id)
            message_deduplication_id: Optional for FIFO topics (auto-generated if not provided)

        Returns:
            AWS SNS publish response containing:
            - MessageId: str
            - SequenceNumber: str (for FIFO topics)

        Raises:
            SNSPublishError: If publishing fails
        """
        try:
            # Construct topic ARN
            topic_arn = self._construct_topic_arn(topic_name)

            # Serialize message to JSON
            message_json = json.dumps(message, indent=2)

            # Prepare publish parameters
            publish_params: Dict[str, Any] = {
                'TopicArn': topic_arn,
                'Message': message_json
            }

            # Add optional subject
            if subject:
                publish_params['Subject'] = subject

            # Add message attributes if provided
            if message_attributes:
                publish_params['MessageAttributes'] = self._format_message_attributes(
                    message_attributes
                )

            # Handle FIFO topic parameters
            if topic_name.endswith('.fifo'):
                # Message Group ID is required for FIFO
                group_id = message_group_id or settings.sns_default_message_group_id
                publish_params['MessageGroupId'] = group_id

                # Deduplication ID (auto-generate if not provided)
                if message_deduplication_id:
                    publish_params['MessageDeduplicationId'] = message_deduplication_id
                else:
                    publish_params['MessageDeduplicationId'] = self._generate_deduplication_id()

            # Publish message
            response = self.sns_client.publish(**publish_params)

            logger.info(
                "Published message to SNS topic '%s' - MessageId: %s",
                topic_name,
                response.get('MessageId', 'unknown')
            )

            return response

        except (BotoCoreError, ClientError) as e:
            error_msg = f"Failed to publish to SNS topic '{topic_name}': {str(e)}"
            logger.error(error_msg)
            raise SNSPublishError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error publishing to SNS topic '{topic_name}': {str(e)}"
            logger.error(error_msg)
            raise SNSPublishError(error_msg) from e

    def send_to_sqs(
        self,
        queue_name: str,
        message: Dict[str, Any],
        message_attributes: Optional[Dict[str, Any]] = None,
        delay_seconds: int = 0,
        message_group_id: Optional[str] = None,
        message_deduplication_id: Optional[str] = None,
        queue_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a JSON message to SQS queue.

        The message format sent will be:
        {
            "message_id": "msg_<timestamp>",
            "timestamp": "<ISO8601 timestamp>",
            "type": "<from message or 'default'>",
            "data": {
                "pr_id": "<report_id>",
                "content": "<message content>",
                "priority": "<priority level>"
            }
        }

        Args:
            queue_name: Name of the SQS queue (used for FIFO detection and logging; required)
            message: JSON message dictionary to send. Should contain:
                     - For task processing: {"pr_id": str, "content": str, "priority": str}
                     - For report updates: {"report_id": str, "workflow_id": str, "status": str}
            message_attributes: Optional message attributes dictionary
            delay_seconds: Delay before message becomes visible (0-900 seconds)
            message_group_id: Required for FIFO queues (defaults to 'default-group')
            message_deduplication_id: Optional for FIFO queues (auto-generated if not provided)
            queue_url: Optional full SQS queue URL; if set, used directly instead of resolving from queue_name

        Returns:
            AWS SQS send_message response containing:
            - MessageId: str
            - MD5OfMessageBody: str
            - SequenceNumber: str (for FIFO queues)

        Raises:
            SQSPublishError: If sending fails
        """
        try:
            # Use queue_url if provided, else resolve from queue name
            if queue_url is not None and queue_url.strip():
                queue_url = queue_url.strip()
            else:
                url_response = self.sqs_client.get_queue_url(QueueName=queue_name)
                queue_url = url_response['QueueUrl']

            # Serialize message to JSON
            message_json = json.dumps(message, indent=2)

            # Prepare send parameters
            send_params: Dict[str, Any] = {
                'QueueUrl': queue_url,
                'MessageBody': message_json
            }

            # Add message attributes if provided
            if message_attributes:
                send_params['MessageAttributes'] = self._format_message_attributes(
                    message_attributes
                )

            # Add delay if specified
            if delay_seconds > 0:
                send_params['DelaySeconds'] = min(delay_seconds, 900)  # Max 15 minutes

            # Handle FIFO queue parameters
            if queue_name.endswith('.fifo'):
                # Message Group ID is required for FIFO
                group_id = message_group_id or 'default-group'
                send_params['MessageGroupId'] = group_id

                # Deduplication ID (auto-generate if not provided)
                if message_deduplication_id:
                    send_params['MessageDeduplicationId'] = message_deduplication_id
                else:
                    send_params['MessageDeduplicationId'] = self._generate_deduplication_id()

            # Send message
            response = self.sqs_client.send_message(**send_params)

            logger.info(
                "Sent message to SQS queue '%s' - MessageId: %s",
                queue_name,
                response.get('MessageId', 'unknown')
            )

            return response

        except (BotoCoreError, ClientError) as e:
            error_msg = f"Failed to send to SQS queue '{queue_name}': {str(e)}"
            logger.error(error_msg)
            raise SQSPublishError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error sending to SQS queue '{queue_name}': {str(e)}"
            logger.error(error_msg)
            raise SQSPublishError(error_msg) from e

    def publish_workflow_event(
        self,
        event_type: str,
        workflow_id: str,
        report_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        Convenience method to publish a workflow event to the configured topic.

        Args:
            event_type: Type of event (e.g., 'workflow_created', 'workflow_completed')
            workflow_id: ID of the workflow
            report_id: Optional report ID
            payload: Optional additional payload data
            priority: Message priority ('low', 'normal', 'high')

        Returns:
            AWS SNS publish response
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        message: Dict[str, Any] = {
            "message_id": f"msg_{timestamp}",
            "timestamp": timestamp,
            "type": event_type,
            "data": {
                "pr_id": report_id or workflow_id,
                "workflow_id": workflow_id,
                "content": f"Workflow event: {event_type}",
                "priority": priority
            }
        }

        if payload:
            message["data"].update(payload)

        return self.publish_to_sns(
            topic_name=settings.report_update_topic_name,
            message=message,
            subject="workflow_task",
            message_group_id=settings.sns_default_message_group_id
        )

    def send_assembly_task(
        self,
        report_id: str,
        workflow_id: str,
        cpm_id: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Convenience method to send an assembly task to the assembler queue.

        This follows the exact message format expected by the consumer:
        {
            "tracker": {"report_id": str, "workflow_id": str},
            "create_data": {"content_product_name": str},
            "payload_id": str
        }

        Args:
            report_id: ID of the report to assemble
            workflow_id: ID of the workflow (used as payload_id)
            cpm_id: Content product name/ID
            additional_data: Optional additional data to include

        Returns:
            AWS SQS send_message response
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        message: Dict[str, Any] = {
            "message_id": f"msg_{timestamp}",
            "timestamp": timestamp,
            "type": "assembly",
            "tracker": {
                "report_id": report_id,
                "workflow_id": workflow_id
            },
            "create_data": {
                "content_product_name": cpm_id or ""
            },
            "payload_id": workflow_id
        }

        if additional_data:
            message.update(additional_data)

        return self.send_to_sqs(
            queue_name=settings.assembler_queue_name,
            message=message
        )


# Singleton instance for convenience
_publisher_instance: Optional[MessagePublisher] = None


def get_publisher() -> MessagePublisher:
    """
    Get the singleton MessagePublisher instance.

    Returns:
        MessagePublisher: The singleton publisher instance
    """
    global _publisher_instance
    if _publisher_instance is None:
        _publisher_instance = MessagePublisher()
    return _publisher_instance
