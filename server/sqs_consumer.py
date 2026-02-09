"""
SQS Message Consumer Module
Consumes messages from AWS SQS queue and processes them through the agent
"""

import json
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
            logger.warning(f"⚠ Config file not found: {sanitize_log_input(str(config_path))}")
            return {}
    except Exception as e:
        # codeql[py/log-injection]
        logger.warning(f"⚠ Error loading config file: {sanitize_log_input(str(e))}")
        return {}


class SQSMessageConsumer:
    """Consumer for SQS messages that integrates with the Workflow Agent"""
    
    def __init__(
        self,
        region: str = "ap-south-2",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        message_handler: Optional[Callable[[str], Dict[str, Any]]] = None
    ):
        """
        Initialize the message consumer for AWS
        
        Args:
            region: AWS region (default: ap-south-2)
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
        logger.info(f"✅ SQS Consumer initialized for region: {sanitize_log_input(region)}")
    
    def stop(self):
        """Stop the consumer gracefully"""
        self.running = False
        logger.info("🛑 Consumer stop requested")
    
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
                logger.error(f"✗ Error getting queue URL: {sanitize_log_input(str(e))}")
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
            logger.error(f"✗ Error receiving messages from queue '{sanitize_log_input(queue_name)}': {sanitize_log_input(str(e))}")
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
            logger.error(f"✗ Error processing message: {sanitize_log_input(str(e))}")
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
            logger.error(f"✗ Error deleting message: {sanitize_log_input(str(e))}")
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
                                    logger.info(f"✓ Message deleted")
                        elif not auto_delete:
                            logger.info(f"⚠ Message NOT deleted (auto_delete=False)")
                
                # Wait before next poll (only if not using long polling)
                if wait_time_seconds == 0:
                    time.sleep(poll_interval)
                    
            except KeyboardInterrupt:
                logger.info("\n⚠ Received interrupt signal, stopping...")
                self.running = False
                break
            except Exception as e:
                # codeql[py/log-injection]
                logger.error(f"✗ Error in consumption loop: {sanitize_log_input(str(e))}")
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
    
    return SQSMessageConsumer(
        region=config.get('region', 'ap-south-2'),
        aws_access_key_id=config.get('credentials', {}).get('access_key_id'),
        aws_secret_access_key=config.get('credentials', {}).get('secret_access_key'),
        aws_session_token=config.get('credentials', {}).get('session_token'),
        message_handler=message_handler
    )

