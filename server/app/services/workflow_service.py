# services/workflow_service.py
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

class WorkflowService:
    @staticmethod
    def get_workflow_stage_permissions() -> Dict[str, Dict[str, bool]]:
        """
        Returns a mapping of workflow stages to user role permissions.

        Returns:
            Dict containing stages as keys and role permission mappings as values
        """
        return {
            "Initial Draft": {
                "GCC Associate": True,
                "Ratings Associate": True,
                "Lead Author": True,
                "Copy Editor": True,
                "Internal Reviewer": True
            },
            "Final Draft": {
                "GCC Associate": True,
                "Ratings Associate": True,
                "Lead Author": True,
                "Copy Editor": True,
                "Internal Reviewer": True
            },
            "Finalize Report": {
                "GCC Associate": False,
                "Ratings Associate": False,
                "Lead Author": True,
                "Copy Editor": False,
                "Internal Reviewer": False
            },
            "Copy Editing": {
                "GCC Associate": False,
                "Ratings Associate": False,
                "Lead Author": False,
                "Copy Editor": True,
                "Internal Reviewer": False
            },
            "L1 Approval": {
                "GCC Associate": False,
                "Ratings Associate": False,
                "Lead Author": False,
                "Copy Editor": False,
                "Internal Reviewer": True
            },
            "Internal Final Review": {
                "GCC Associate": False,
                "Ratings Associate": False,
                "Lead Author": True,
                "Copy Editor": False,
                "Internal Reviewer": False
            },
            "In Publication": {
                "GCC Associate": False,
                "Ratings Associate": False,
                "Lead Author": True,
                "Copy Editor": False,
                "Internal Reviewer": False
            },
            "Publication Failed": {
                "GCC Associate": False,
                "Ratings Associate": False,
                "Lead Author": True,
                "Copy Editor": False,
                "Internal Reviewer": False
            }
        }

    @staticmethod
    async def get_workflow_json_from_workflow(db: AsyncSession, workflow_id: int) -> Dict[str, Any]:
        """
        Get workflow JSON by workflow_id from the workflow table.
        
        Args:
            db: Database session
            workflow_id: The ID of the workflow to retrieve
            
        Returns:
            Dict containing the workflow JSON or empty dict if not found
        """
        try:
            print(f"[DEBUG] Fetching workflow with ID: {workflow_id}")
            
            # First, check if the table exists
            table_exists = await db.execute(
                text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'workflow'
                )
                """)
            )
            if not table_exists.scalar():
                print("[ERROR] Table 'public.workflow' does not exist")
                return {}
                
            # Check if workflow exists
            workflow_exists = await db.execute(
                text("SELECT EXISTS (SELECT 1 FROM public.workflow WHERE workflow_id = :workflow_id)"),
                {"workflow_id": workflow_id}
            )
            if not workflow_exists.scalar():
                print(f"[WARNING] No workflow found with ID: {workflow_id}")
                return {}
                
            # Get the workflow data
            result = await db.execute(
                text("SELECT workflow_json FROM public.workflow WHERE workflow_id = :workflow_id"),
                {"workflow_id": workflow_id}
            )
            row = result.fetchone()
            
            print(f"[DEBUG] Raw row data: {row}")
            
            if not row or not row[0]:
                print("[WARNING] No workflow data found")
                return {}
                
            workflow_data = row[0]
            print(f"[DEBUG] Found workflow data: {workflow_data}")
            
            # If it's already a list or dict, return it directly
            if isinstance(workflow_data, (dict, list)):
                print(f"[DEBUG] Returning workflow data as {type(workflow_data).__name__}")
                return workflow_data
                
            # If it's a string, try to parse it as JSON
            if isinstance(workflow_data, str):
                try:
                    data = json.loads(workflow_data)
                    print(f"[DEBUG] Successfully parsed JSON from string")
                    return data if isinstance(data, (dict, list)) else {}
                except json.JSONDecodeError as e:
                    print(f"[ERROR] Failed to parse workflow JSON: {e}")
                    return {}
            
            # If we get here, it's an unexpected type
            print(f"[ERROR] Unexpected workflow data type: {type(workflow_data)}")
            return {}
            
        except Exception as e:
            # Log the error (you might want to add proper logging)
            print(f"Error fetching workflow {workflow_id}: {str(e)}")
            raise