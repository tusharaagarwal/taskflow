"""
Workflow Message Handlers for AWS Messaging Service
Handles business logic for processing SQS/SNS messages
"""

import logging
from typing import Dict, Any
from datetime import datetime, timezone
from app.services.aws_messaging_service import MessageType, aws_messaging_service
from app.services.report_tracker_service import ReportTrackerService
from app.utils.security import sanitize_log_input

logger = logging.getLogger(__name__)


class WorkflowMessageHandlers:
    """Handlers for workflow messages"""
    
    def __init__(self):
        self.report_tracker_service = ReportTrackerService()
    
    async def handle_assembler_completion(self, message: Dict[str, Any]):
        """
        Handle Assembler completion messages
        Moves report to second step in workflow
        """
        try:
            logger.info(f"Processing Assembler completion message: {sanitize_log_input(str(message))}")
            
            # Extract report information
            report_id = message.get('report_id')
            if not report_id:
                logger.error("No report_id found in Assembler completion message")
                return
            
            # Update report status to indicate first draft completed
            update_data = {
                'status': 'first_draft_completed',
                'assembler_completed_at': datetime.now(timezone.utc).isoformat(),
                'next_step': 'second_step_processing'
            }
            
            # Update report in tracker
            success = await self.report_tracker_service.update_report(report_id, update_data)
            
            if success:
                logger.info(f"Successfully processed Assembler completion for report {sanitize_log_input(str(report_id))}")
                
                # Publish update notification
                await aws_messaging_service.publish_report_update(
                    report_id=report_id,
                    update_type='assembler_completion',
                    data={
                        'status': 'first_draft_completed',
                        'next_step': 'second_step_processing'
                    }
                )
                
                # Trigger second step processing (this would integrate with your workflow logic)
                await self._trigger_second_step_processing(report_id)
                
            else:
                logger.error(f"Failed to update report {sanitize_log_input(str(report_id))} after Assembler completion")
                
        except Exception as e:
            logger.error(f"Error handling Assembler completion: {sanitize_log_input(str(e))}")
    
    async def handle_endpoint_pr_event(self, message: Dict[str, Any]):
        """
        Handle Endpoint PR event messages
        Starts report creation or tracking process
        """
        try:
            logger.info(f"Processing Endpoint PR event message: {sanitize_log_input(str(message))}")
            
            # Extract PR information
            pr_id = message.get('pr_id')
            event_type = message.get('event_type', 'approved')
            
            if not pr_id:
                logger.error("No pr_id found in Endpoint PR event message")
                return
            
            if event_type.lower() == 'approved':
                # Start report creation process
                await self._start_report_creation(pr_id)
            else:
                logger.info(f"Ignoring non-approved PR event: {sanitize_log_input(str(event_type))}")
                
        except Exception as e:
            logger.error(f"Error handling Endpoint PR event: {sanitize_log_input(str(e))}")
    
    async def _trigger_second_step_processing(self, report_id: str):
        """
        Trigger second step processing for a report
        This would integrate with your workflow orchestration logic
        """
        try:
            logger.info(f"Triggering second step processing for report {sanitize_log_input(str(report_id))}")
            
            # Update report status
            update_data = {
                'status': 'second_step_in_progress',
                'second_step_started_at': datetime.now(timezone.utc).isoformat()
            }
            
            await self.report_tracker_service.update_report(report_id, update_data)
            
            # Publish update
            await aws_messaging_service.publish_report_update(
                report_id=report_id,
                update_type='second_step_started',
                data={'status': 'second_step_in_progress'}
            )
            
            # Here you would integrate with your actual second step processing logic
            # For example, calling another service, queueing a job, etc.
            
        except Exception as e:
            logger.error(f"Error triggering second step processing: {sanitize_log_input(str(e))}")
    
    async def _start_report_creation(self, pr_id: str):
        """
        Start the report creation process for an approved PR
        """
        try:
            logger.info(f"Starting report creation for PR {sanitize_log_input(str(pr_id))}")
            
            # Create new report entry
            report_data = {
                'pr_id': pr_id,
                'status': 'report_creation_started',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'workflow_step': 'first_draft'
            }
            
            # Create report in tracker
            report = await self.report_tracker_service.create_report(report_data)
            
            if report:
                report_id = report.get('id')
                logger.info(f"Created report {sanitize_log_input(str(report_id))} for PR {sanitize_log_input(str(pr_id))}")
                
                # Publish update
                await aws_messaging_service.publish_report_update(
                    report_id=report_id,
                    update_type='report_created',
                    data={
                        'pr_id': pr_id,
                        'status': 'report_creation_started',
                        'workflow_step': 'first_draft'
                    }
                )
                
                # Trigger first draft creation (this would integrate with Assembler)
                await self._trigger_first_draft_creation(report_id, pr_id)
            else:
                logger.error(f"Failed to create report for PR {sanitize_log_input(str(pr_id))}")
                
        except Exception as e:
            logger.error(f"Error starting report creation: {sanitize_log_input(str(e))}")
    
    async def _trigger_first_draft_creation(self, report_id: str, pr_id: str):
        """
        Trigger first draft creation for a report
        This would integrate with the Assembler service
        """
        try:
            logger.info(f"Triggering first draft creation for report {sanitize_log_input(str(report_id))} (PR {sanitize_log_input(str(pr_id))})")
            
            # Update report status
            update_data = {
                'status': 'first_draft_in_progress',
                'first_draft_started_at': datetime.now(timezone.utc).isoformat()
            }
            
            await self.report_tracker_service.update_report(report_id, update_data)
            
            # Publish update
            await aws_messaging_service.publish_report_update(
                report_id=report_id,
                update_type='first_draft_started',
                data={
                    'pr_id': pr_id,
                    'status': 'first_draft_in_progress'
                }
            )
            
            # Here you would integrate with your actual Assembler service
            # For example, sending a message to Assembler queue, calling Assembler API, etc.
            
        except Exception as e:
            logger.error(f"Error triggering first draft creation: {sanitize_log_input(str(e))}")


# Create global instance
workflow_handlers = WorkflowMessageHandlers()


def register_message_handlers():
    """Register all message handlers with the AWS messaging service"""
    aws_messaging_service.register_handler(
        MessageType.ASSEMBLER_COMPLETION,
        workflow_handlers.handle_assembler_completion
    )
    
    aws_messaging_service.register_handler(
        MessageType.ENDPOINT_PR_EVENT,
        workflow_handlers.handle_endpoint_pr_event
    )
    
    logger.info("All message handlers registered successfully")
