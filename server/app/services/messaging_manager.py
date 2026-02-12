"""
Messaging Manager for Workflow Orchestrator
Manages the lifecycle of SQS/SNS listeners and publishers
"""

import asyncio
import logging
from typing import Optional
from app.services.aws_messaging_service import aws_messaging_service, AWSConfig
from app.services.workflow_message_handlers import register_message_handlers
from app.config.config import settings
from app.utils.security import sanitize_log_input

logger = logging.getLogger(__name__)


class MessagingManager:
    """Manages messaging services for the Workflow Orchestrator"""
    
    def __init__(self):
        self.config = self._load_aws_config()
        self.messaging_service = aws_messaging_service
        self._listeners_running = False
        self._listener_tasks: Optional[list] = None
    
    def _load_aws_config(self) -> AWSConfig:
        """Load AWS configuration from settings"""
        return AWSConfig(
            region=getattr(settings, 'aws_region', 'ap-south-1'),
            access_key_id=getattr(settings, 'aws_access_key_id', None),
            secret_access_key=getattr(settings, 'aws_secret_access_key', None),
            session_token=getattr(settings, 'aws_session_token', None),
            assembler_queue=getattr(settings, 'assembler_queue_name', 'orchestrator-to-assembler'),
            endpoint_queue=getattr(settings, 'endpoint_queue_name', 'WorkflowOrchestratorEndpoint'),
            report_update_topic=getattr(settings, 'report_update_topic_name', 'workflow_orchestrator_updates')
        )
    
    async def initialize(self):
        """Initialize messaging services"""
        try:
            logger.info("Initializing messaging services...")
            
            # Register message handlers
            register_message_handlers()
            
            # Update messaging service config
            self.messaging_service.config = self.config
            
            logger.info("Messaging services initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize messaging services: {sanitize_log_input(str(e))}")
            raise
    
    async def start_listeners(self):
        """Start all SQS listeners"""
        try:
            if self._listeners_running:
                logger.warning("Listeners are already running")
                return
            
            logger.info("Starting SQS listeners...")
            
            # Create tasks for each listener
            self._listener_tasks = [
                asyncio.create_task(self.messaging_service.start_assembler_listener()),
                asyncio.create_task(self.messaging_service.start_endpoint_listener())
            ]
            
            self._listeners_running = True
            logger.info("All SQS listeners started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start listeners: {sanitize_log_input(str(e))}")
            await self.stop_listeners()
            raise
    
    async def stop_listeners(self):
        """Stop all SQS listeners"""
        try:
            if not self._listeners_running:
                logger.info("Listeners are not running")
                return
            
            logger.info("Stopping SQS listeners...")
            
            # Stop the consumer
            self.messaging_service.stop_all_listeners()
            
            # Cancel listener tasks
            if self._listener_tasks:
                for task in self._listener_tasks:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                
                self._listener_tasks = None
            
            self._listeners_running = False
            logger.info("All SQS listeners stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping listeners: {sanitize_log_input(str(e))}")
    
    async def publish_report_update(
        self,
        report_id: str,
        update_type: str,
        data: dict,
        subject: Optional[str] = None
    ):
        """Publish a report update to SNS"""
        try:
            await self.messaging_service.publish_report_update(
                report_id=report_id,
                update_type=update_type,
                data=data,
                subject=subject
            )
            logger.info(f"Published report update for {sanitize_log_input(report_id)}: {sanitize_log_input(update_type)}")
            
        except Exception as e:
            logger.error(f"Failed to publish report update: {sanitize_log_input(str(e))}")
            raise
    
    def is_running(self) -> bool:
        """Check if listeners are running"""
        return self._listeners_running
    
    async def health_check(self) -> dict:
        """Perform health check on messaging services"""
        try:
            # Check if listeners are running
            listeners_status = "running" if self._listeners_running else "stopped"
            
            # Check AWS connectivity (optional - could add actual AWS health check)
            aws_connectivity = "connected"  # Placeholder
            
            return {
                "status": "healthy",
                "listeners": listeners_status,
                "aws_connectivity": aws_connectivity,
                "config": {
                    "assembler_queue": self.config.assembler_queue,
                    "endpoint_queue": self.config.endpoint_queue,
                    "report_update_topic": self.config.report_update_topic,
                    "region": self.config.region
                }
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {sanitize_log_input(str(e))}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global instance
messaging_manager = MessagingManager()
