"""
SQS Message Consumer Module
Consumes messages from AWS SQS queue and processes them through the agent

DEPRECATED: This module is deprecated. A copy is kept for reference in
server/deprecated/sqs_consumer_deprecated.py. Assembler completion consumption
now uses app/services/sqs_consumer.py (in-process, started in FastAPI lifespan).
Agent service still imports this module; prefer migrating to the new consumer when possible.
"""
import warnings

warnings.warn(
    "server.sqs_consumer is deprecated. See server/deprecated/sqs_consumer_deprecated.py "
    "for reference; assembler completion uses app.services.sqs_consumer (in-process).",
    DeprecationWarning,
    stacklevel=2,
)

import json
import os
import boto3
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable
import time
import logging
from pathlib import Path

from app.utils.security import sanitize_log_input

logger = logging.getLogger("sqs_consumer")
_credentials_tip_logged = False


def load_aws_config(config_file: str = "aws_config.json") -> Dict[str, Any]:
    """
    Load AWS configuration from JSON file
    
    Args:
        config_file: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    try:
        # Try to load from same directory as script
        script_dir = Path(__file__).parent
        config_path = script_dir / config_file
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        else:
            # codeql[py/log-injection]
            logger.warning(f"[WARN] Config file not found: {sanitize_log_input(str(config_path))}")
            return {}
    except Exception as e:
        # codeql[py/log-injection]
        logger.warning(f"[WARN] Error loading config file: {sanitize_log_input(str(e))}")
        return {}


class SQSMessageConsumer:
    """Consumer for SQS messages that integrates with the Workflow Agent"""
    
    def __init__(
        self,
        region: str = "ap-south-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        message_handler: Optional[Callable[[str], Dict[str, Any]]] = None
    ):
        """
        Initialize the message consumer for AWS
        
        Args:
            region: AWS region (default: ap-south-1)
            aws_access_key_id: AWS access key (None to use default credentials)
            aws_secret_access_key: AWS secret key (None to use default credentials)
            aws_session_token: AWS session token (for temporary credentials)
            message_handler: Function to process message content (e.g., run_agent)
        """
        self.region = region
        self.running = True
        self.message_handler = message_handler
        
        # Prepare client configuration
        client_config = {
            'region_name': region
        }
        
        # Add credentials if provided
        if aws_access_key_id and aws_secret_access_key:
            client_config['aws_access_key_id'] = aws_access_key_id
            client_config['aws_secret_access_key'] = aws_secret_access_key
            if aws_session_token:
                client_config['aws_session_token'] = aws_session_token
        
        # Initialize SQS client
        self.sqs_client = boto3.client('sqs', **client_config)
        
        # Statistics
        self.stats = {
            'received': 0,
            'processed': 0,
            'failed': 0,
            'deleted': 0
        }
        
        # codeql[py/log-injection]
        logger.info(f"[OK] SQS Consumer initialized for region: {sanitize_log_input(region)}")

    def stop(self):
        """Stop the consumer gracefully"""
        self.running = False
        logger.info("[STOP] Consumer stop requested")

    def receive_messages(
        self,
        queue_name: str,
        max_messages: int = 10,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Receive messages from SQS queue
        
        Args:
            queue_name: Name of the SQS queue
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time
            visibility_timeout: Visibility timeout for received messages
            
        Returns:
            List of messages
        """
        try:
            # Get queue URL from queue name
            try:
                response = self.sqs_client.get_queue_url(QueueName=queue_name)
                queue_url = response['QueueUrl']
            except Exception as e:
                # codeql[py/log-injection]
                logger.error(f"[ERROR] Error getting queue URL: {sanitize_log_input(str(e))}")
                global _credentials_tip_logged
                err_msg = str(e)
                if ("InvalidClientTokenId" in err_msg or "security token" in err_msg.lower() or "expired" in err_msg.lower()) and not _credentials_tip_logged:
                    _credentials_tip_logged = True
                    logger.info(
                        "Tip: Credentials invalid/expired. "
                        "1) Run: aws sso login --profile YOUR_AWS_SSO_PROFILE  "
                        "2) From repo root: .\\scripts\\refresh_aws_credentials.ps1 -Profile YOUR_AWS_SSO_PROFILE  "
                        "3) Restart this consumer (Ctrl+C then run again)."
                    )
                return []
            
            # Receive messages
            response = self.sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
                VisibilityTimeout=visibility_timeout,
                AttributeNames=['All'],
                MessageAttributeNames=['All']
            )
            
            messages = response.get('Messages', [])
            self.stats['received'] += len(messages)
            
            return messages
            
        except Exception as e:
            # codeql[py/log-injection]
            logger.error(f"[ERROR] Error receiving messages from queue '{sanitize_log_input(queue_name)}': {sanitize_log_input(str(e))}")
            return []

    def extract_message_content(self, message: Dict[str, Any]) -> str:
        """
        Extract the actual message content from SQS message
        
        Args:
            message: Raw SQS message
            
        Returns:
            Extracted message content as string
        """
        body = message.get('Body', '{}')
        
        try:
            body_json = json.loads(body)
        except json.JSONDecodeError:
            return body
        
        # Check if message is from SNS
        if isinstance(body_json, dict) and body_json.get('Type') == 'Notification':
            # Extract SNS message
            sns_message = body_json.get('Message', '')
            try:
                actual_message = json.loads(sns_message)
                # If it's a dict with a 'command' or 'message' field, extract it
                if isinstance(actual_message, dict):
                    return actual_message.get('command') or actual_message.get('message') or json.dumps(actual_message)
                return sns_message
            except json.JSONDecodeError:
                return sns_message
        else:
            # Direct SQS message
            if isinstance(body_json, dict):
                return body_json.get('command') or body_json.get('message') or json.dumps(body_json)
            return body
    
    def process_message(self, message: Dict[str, Any]) -> bool:
        """
        Process a single message through the agent
        
        Args:
            message: Message to process
            
        Returns:
            True if processing successful, False otherwise
        """
        try:
            message_id = message.get('MessageId', 'unknown')
            content = self.extract_message_content(message)
            
            sanitized_content = sanitize_log_input(content)
            # codeql[py/log-injection]
            logger.info(f"📨 Processing message (ID: {sanitize_log_input(str(message_id))})")
            logger.info(f"   Content: {sanitized_content[:200]}..." if len(sanitized_content) > 200 else f"   Content: {sanitized_content}")
            
            # Process through agent if handler is available
            if self.message_handler:
                result = self.message_handler(content)
                # codeql[py/log-injection]
                logger.info(f"   Agent Response: {sanitize_log_input(json.dumps(result, default=str))[:500]}")
            else:
                logger.warning("   No message handler configured - message logged but not processed")
            
            self.stats['processed'] += 1
            return True
            
        except Exception as e:
            # codeql[py/log-injection]
            logger.error(f"[ERROR] Error processing message: {sanitize_log_input(str(e))}")
            self.stats['failed'] += 1
            return False
    
    def delete_message(self, queue_name: str, receipt_handle: str) -> bool:
        """
        Delete a message from the queue
        
        Args:
            queue_name: Name of the SQS queue
            receipt_handle: Receipt handle of the message
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            # Get queue URL from queue name
            try:
                response = self.sqs_client.get_queue_url(QueueName=queue_name)
                queue_url = response['QueueUrl']
            except Exception as e:
                # codeql[py/log-injection]
                logger.error(f"✗ Error getting queue URL: {sanitize_log_input(str(e))}")
                return False
            
            self.sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            
            self.stats['deleted'] += 1
            return True
            
        except Exception as e:
            # codeql[py/log-injection]
            logger.error(f"[ERROR] Error deleting message: {sanitize_log_input(str(e))}")
            return False

    def consume_continuously(
        self,
        queue_name: str,
        auto_delete: bool = True,
        max_messages: int = 10,
        wait_time_seconds: int = 20,
        poll_interval: int = 1
    ):
        """
        Continuously consume messages from queue
        
        Args:
            queue_name: Name of the SQS queue
            auto_delete: Whether to automatically delete processed messages
            max_messages: Maximum number of messages to receive per poll
            wait_time_seconds: Long polling wait time
            poll_interval: Interval between polls (seconds)
        """
        # codeql[py/log-injection]
        logger.info(f"🔄 Starting continuous consumption from queue: {sanitize_log_input(queue_name)}")
        logger.info(f"   Auto-delete: {auto_delete}")
        logger.info(f"   Max messages per poll: {max_messages}")
        logger.info(f"   Long polling wait time: {wait_time_seconds}s")
        
        while self.running:
            try:
                # Receive messages
                messages = self.receive_messages(
                    queue_name=queue_name,
                    max_messages=max_messages,
                    wait_time_seconds=wait_time_seconds
                )
                
                if messages:
                    logger.info(f"📥 Received {len(messages)} message(s) at {datetime.now(timezone.utc).isoformat()}")
                    
                    for message in messages:
                        # Process message
                        success = self.process_message(message)
                        
                        # Delete message if processing successful and auto_delete enabled
                        if success and auto_delete:
                            receipt_handle = message.get('ReceiptHandle')
                            if receipt_handle:
                                if self.delete_message(queue_name, receipt_handle):
                                    logger.info("Message deleted")
                        elif not auto_delete:
                            logger.info("[WARN] Message NOT deleted (auto_delete=False)")

                # Wait before next poll (only if not using long polling)
                if wait_time_seconds == 0:
                    time.sleep(poll_interval)
                    
            except KeyboardInterrupt:
                logger.info("\n[WARN] Received interrupt signal, stopping...")
                self.running = False
                break
            except Exception as e:
                # codeql[py/log-injection]
                logger.error(f"[ERROR] Error in consumption loop: {sanitize_log_input(str(e))}")
                time.sleep(poll_interval)
    
    def get_stats(self) -> Dict[str, int]:
        """Get consumption statistics"""
        return self.stats.copy()
    
    def print_stats(self):
        """Print consumption statistics"""
        logger.info("=" * 60)
        logger.info("CONSUMPTION STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Messages received:  {self.stats['received']}")
        logger.info(f"Messages processed: {self.stats['processed']}")
        logger.info(f"Messages failed:    {self.stats['failed']}")
        logger.info(f"Messages deleted:   {self.stats['deleted']}")
        logger.info("=" * 60)


def create_consumer_from_config(
    config_file: str = "aws_config.json",
    message_handler: Optional[Callable[[str], Dict[str, Any]]] = None
) -> Optional[SQSMessageConsumer]:
    """
    Create an SQS consumer using configuration from file
    
    Args:
        config_file: Path to AWS config file
        message_handler: Function to handle messages
        
    Returns:
        Configured SQSMessageConsumer or None if config not found
    """
    config = load_aws_config(config_file)
    
    if not config:
        logger.error("Failed to load AWS configuration")
        return None

    # Prefer env vars (e.g. after refresh_aws_credentials or SSO), then config file, then None = boto3 default chain
    creds = config.get("credentials") or {}
    aws_access_key_id = (os.environ.get("AWS_ACCESS_KEY_ID") or (creds.get("access_key_id") or "").strip() or None)
    aws_secret_access_key = (os.environ.get("AWS_SECRET_ACCESS_KEY") or (creds.get("secret_access_key") or "").strip() or None)
    aws_session_token = (os.environ.get("AWS_SESSION_TOKEN") or (creds.get("session_token") or "").strip() or None)

    return SQSMessageConsumer(
        region=config.get('region', 'ap-south-1'),
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_session_token=aws_session_token,
        message_handler=message_handler
    )


def _configure_logging() -> None:
    """Configure logging so output appears in the terminal."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)


if __name__ == "__main__":
    import argparse
    _configure_logging()

    parser = argparse.ArgumentParser(description="SQS consumer (standalone). Consumes from queue in aws_config.json.")
    parser.add_argument("--config-file", default="aws_config.json", help="Path to AWS config JSON")
    parser.add_argument("--queue", help="Queue name (default: from config resources.sqs_queue)")
    parser.add_argument("--wait-time", type=int, default=20, help="Long polling wait time in seconds")
    args = parser.parse_args()

    config = load_aws_config(args.config_file)
    if not config:
        print("Error: Could not load AWS config. Check aws_config.json and credentials.", file=sys.stderr)
        sys.exit(1)

    queue_name = args.queue or config.get("resources", {}).get("sqs_queue")
    if not queue_name:
        print("Error: No queue name. Set --queue or resources.sqs_queue in config.", file=sys.stderr)
        sys.exit(1)

    consumer = create_consumer_from_config(args.config_file)
    if not consumer:
        sys.exit(1)

    def _shutdown(*_):
        consumer.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Starting SQS consumer (Ctrl+C to stop)")
    logger.info("Queue: %s", queue_name)
    try:
        consumer.consume_continuously(
            queue_name=queue_name,
            wait_time_seconds=args.wait_time,
            auto_delete=True,
        )
    finally:
        consumer.print_stats()
    logger.info("Exited.")

