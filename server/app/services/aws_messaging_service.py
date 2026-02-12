"""
AWS Messaging Service for Workflow Orchestrator
Handles SQS queue consumption and SNS topic publishing
"""

import json
import boto3
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import logging
from app.config.config import settings
from app.utils.security import sanitize_log_input

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Message types for workflow orchestration"""
    ASSEMBLER_COMPLETION = "assembler_completion"
    ENDPOINT_PR_EVENT = "endpoint_pr_event"
    REPORT_UPDATE = "report_update"


@dataclass
class AWSConfig:
    """AWS configuration"""
    region: str = "ap-south-1"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    session_token: Optional[str] = None
    
    # Queue and topic names
    assembler_queue: str = "orchestrator-to-assembler"
    endpoint_queue: str = "WorkflowOrchestratorEndpoint"
    report_update_topic: str = "workflow_orchestrator_updates"


class SQSConsumer:
    """SQS Message Consumer"""
    
    def __init__(self, config: AWSConfig):
        self.config = config
        self.client_config = {
            'region_name': config.region
        }
        
        if config.access_key_id and config.secret_access_key:
            self.client_config.update({
                'aws_access_key_id': config.access_key_id,
                'aws_secret_access_key': config.secret_access_key
            })
            if config.session_token:
                self.client_config['aws_session_token'] = config.session_token
        
        self.sqs_client = boto3.client('sqs', **self.client_config)
        self.running = False
        
    async def start_consuming(
        self, 
        queue_name: str, 
        message_handler: Callable[[Dict[str, Any]], bool],
        max_messages: int = 10,
        wait_time_seconds: int = 20
    ):
        """Start continuous message consumption"""
        self.running = True
        logger.info(f"Starting SQS consumer for queue: {sanitize_log_input(queue_name)}")
        
        while self.running:
            try:
                messages = await self._receive_messages(queue_name, max_messages, wait_time_seconds)
                
                for message in messages:
                    try:
                        success = await self._process_message(message, message_handler)
                        if success:
                            await self._delete_message(queue_name, message['ReceiptHandle'])
                    except Exception as e:
                        logger.error(f"Error processing message: {sanitize_log_input(str(e))}")
                        
            except Exception as e:
                logger.error(f"Error in consumption loop: {sanitize_log_input(str(e))}")
                await asyncio.sleep(5)
    
    def stop_consuming(self):
        """Stop message consumption"""
        self.running = False
        logger.info("Stopping SQS consumer")
    
    async def _receive_messages(self, queue_name: str, max_messages: int, wait_time_seconds: int) -> List[Dict[str, Any]]:
        """Receive messages from SQS queue"""
        try:
            response = self.sqs_client.get_queue_url(QueueName=queue_name)
            queue_url = response['QueueUrl']
            
            response = self.sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
                AttributeNames=['All'],
                MessageAttributeNames=['All']
            )
            
            return response.get('Messages', [])
        except Exception as e:
            logger.error(f"Error receiving messages from queue '{sanitize_log_input(queue_name)}': {sanitize_log_input(str(e))}")
            return []
    
    async def _process_message(self, message: Dict[str, Any], handler: Callable) -> bool:
        """Process a single message"""
        try:
            message_id = message.get('MessageId', 'unknown')
            body = message.get('Body', '{}')
            
            # Parse message body
            try:
                body_json = json.loads(body)
            except json.JSONDecodeError:
                body_json = {'raw_body': body}
            
            logger.info(f"Processing message {sanitize_log_input(str(message_id))}")
            return await handler(body_json)
            
        except Exception as e:
            logger.error(f"Error processing message: {sanitize_log_input(str(e))}")
            return False
    
    async def _delete_message(self, queue_name: str, receipt_handle: str):
        """Delete message from queue"""
        try:
            response = self.sqs_client.get_queue_url(QueueName=queue_name)
            queue_url = response['QueueUrl']
            
            self.sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            logger.debug("Message deleted successfully")
        except Exception as e:
            logger.error(f"Error deleting message: {sanitize_log_input(str(e))}")


class SNSPublisher:
    """SNS Message Publisher"""
    
    def __init__(self, config: AWSConfig):
        self.config = config
        self.client_config = {
            'region_name': config.region
        }
        
        if config.access_key_id and config.secret_access_key:
            self.client_config.update({
                'aws_access_key_id': config.access_key_id,
                'aws_secret_access_key': config.secret_access_key
            })
            if config.session_token:
                self.client_config['aws_session_token'] = config.session_token
        
        self.sns_client = boto3.client('sns', **self.client_config)
    
    async def publish_message(
        self,
        topic_name: str,
        message: Dict[str, Any],
        subject: Optional[str] = None,
        message_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Publish message to SNS topic"""
        try:
            # Construct topic ARN if needed
            if not topic_name.startswith('arn:'):
                sts_client = boto3.client('sts', **self.client_config)
                account_id = sts_client.get_caller_identity()['Account']
                topic_arn = f"arn:aws:sns:{self.config.region}:{account_id}:{topic_name}"
            else:
                topic_arn = topic_name
            
            # Prepare message
            message_json = json.dumps(message)
            
            # Prepare publish parameters
            publish_params = {
                'TopicArn': topic_arn,
                'Message': message_json
            }
            
            if subject:
                publish_params['Subject'] = subject
            
            if message_attributes:
                publish_params['MessageAttributes'] = self._format_attributes(message_attributes)
            
            # Publish message
            response = self.sns_client.publish(**publish_params)
            
            logger.info(f"Successfully published to SNS topic '{sanitize_log_input(topic_name)}'")
            logger.debug(f"Message ID: {sanitize_log_input(str(response['MessageId']))}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error publishing to SNS topic '{sanitize_log_input(topic_name)}': {sanitize_log_input(str(e))}")
            raise
    
    def _format_attributes(self, attributes: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """Format message attributes for SNS"""
        formatted = {}
        for key, value in attributes.items():
            if isinstance(value, str):
                formatted[key] = {'DataType': 'String', 'StringValue': value}
            elif isinstance(value, (int, float)):
                formatted[key] = {'DataType': 'Number', 'StringValue': str(value)}
            else:
                formatted[key] = {'DataType': 'String', 'StringValue': json.dumps(value)}
        return formatted


class AWSMessagingService:
    """Main AWS Messaging Service for Workflow Orchestrator"""
    
    def __init__(self, config: Optional[AWSConfig] = None):
        self.config = config or AWSConfig()
        self.consumer = SQSConsumer(self.config)
        self.publisher = SNSPublisher(self.config)
        
        # Message handlers
        self._handlers = {
            MessageType.ASSEMBLER_COMPLETION: [],
            MessageType.ENDPOINT_PR_EVENT: [],
            MessageType.REPORT_UPDATE: []
        }
    
    def register_handler(self, message_type: MessageType, handler: Callable):
        """Register a message handler for a specific message type"""
        self._handlers[message_type].append(handler)
        logger.info(f"Registered handler for {sanitize_log_input(message_type.value)}")
    
    async def start_assembler_listener(self):
        """Start listening for Assembler completion messages"""
        logger.info("Starting Assembler completion listener")
        
        async def assembler_handler(message_body: Dict[str, Any]) -> bool:
            """Handle Assembler completion messages"""
            try:
                # Check if this is an SNS message
                if isinstance(message_body, dict) and message_body.get('Type') == 'Notification':
                    payload = json.loads(message_body.get('Message', '{}'))
                else:
                    payload = message_body
                
                # Call registered handlers
                for handler in self._handlers[MessageType.ASSEMBLER_COMPLETION]:
                    await handler(payload)
                
                return True
            except Exception as e:
                logger.error(f"Error handling Assembler completion: {sanitize_log_input(str(e))}")
                return False
        
        await self.consumer.start_consuming(
            self.config.assembler_queue,
            assembler_handler
        )
    
    async def start_endpoint_listener(self):
        """Start listening for Endpoint SNS messages"""
        logger.info("Starting Endpoint SNS listener")
        
        async def endpoint_handler(message_body: Dict[str, Any]) -> bool:
            """Handle Endpoint SNS messages"""
            try:
                # Check if this is an SNS message
                if isinstance(message_body, dict) and message_body.get('Type') == 'Notification':
                    payload = json.loads(message_body.get('Message', '{}'))
                else:
                    payload = message_body
                
                # Call registered handlers
                for handler in self._handlers[MessageType.ENDPOINT_PR_EVENT]:
                    await handler(payload)
                
                return True
            except Exception as e:
                logger.error(f"Error handling Endpoint PR event: {sanitize_log_input(str(e))}")
                return False
        
        await self.consumer.start_consuming(
            self.config.endpoint_queue,
            endpoint_handler
        )
    
    async def publish_report_update(
        self,
        report_id: str,
        update_type: str,
        data: Dict[str, Any],
        subject: Optional[str] = None
    ):
        """Publish report update to SNS topic"""
        message = {
            'message_type': MessageType.REPORT_UPDATE.value,
            'report_id': report_id,
            'update_type': update_type,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data': data
        }
        
        if not subject:
            subject = f"Report Update: {update_type}"
        
        await self.publisher.publish_message(
            self.config.report_update_topic,
            message,
            subject
        )
    
    def stop_all_listeners(self):
        """Stop all message listeners"""
        self.consumer.stop_consuming()


# Global instance
aws_messaging_service = AWSMessagingService()
