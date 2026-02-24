# services/workflow_service.py
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow
from app.schemas.workflow_schemas import WorkflowUpdateRequest


def _parse_workflow_json(raw: Any) -> Dict[str, Any]:
    """Parse workflow_json column (str or dict) to dict. Returns {} on failure."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


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

    @staticmethod
    def parse_workflow_json_raw(raw: Any) -> Dict[str, Any]:
        """Parse workflow_json column value to dict for API responses."""
        return _parse_workflow_json(raw)

    @staticmethod
    async def get_workflows(
        db: AsyncSession,
        is_active: Optional[bool] = None,
    ) -> List[Workflow]:
        """Return non-soft-deleted workflows, optionally filtered by is_active."""
        stmt = select(Workflow).where(Workflow.deleted_at.is_(None))
        if is_active is not None:
            stmt = stmt.where(Workflow.is_active == is_active)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_workflow_count(
        db: AsyncSession,
        is_active: Optional[bool] = None,
    ) -> int:
        """Return count of non-soft-deleted workflows, optionally filtered by is_active."""
        stmt = select(func.count()).select_from(Workflow).where(Workflow.deleted_at.is_(None))
        if is_active is not None:
            stmt = stmt.where(Workflow.is_active == is_active)
        result = await db.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def get_workflow_by_id(
        db: AsyncSession,
        workflow_id: int,
    ) -> Optional[Workflow]:
        """Fetch single workflow by ID; returns None if not found or soft-deleted."""
        stmt = (
            select(Workflow)
            .where(Workflow.workflow_id == workflow_id)
            .where(Workflow.deleted_at.is_(None))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def resolve_workflow_name(workflow: Workflow) -> Optional[str]:
        """Resolve display name: column name, else workflow_json workflow_name/name, else None."""
        if workflow.name is not None and workflow.name != "":
            return workflow.name
        data = _parse_workflow_json(workflow.workflow_json)
        return data.get("workflow_name") or data.get("name") or None

    @staticmethod
    async def update_workflow(
        db: AsyncSession,
        workflow_id: int,
        data: WorkflowUpdateRequest,
    ) -> Optional[Workflow]:
        """Update only provided fields; returns None if workflow not found or soft-deleted."""
        workflow = await WorkflowService.get_workflow_by_id(db, workflow_id)
        if workflow is None:
            return None
        if data.name is not None:
            workflow.name = data.name
        if data.is_active is not None:
            workflow.is_active = data.is_active
        if data.workflow_json is not None:
            workflow.workflow_json = json.dumps(data.workflow_json)
        await db.commit()
        await db.refresh(workflow)
        return workflow

    @staticmethod
    async def soft_delete_workflow(
        db: AsyncSession,
        workflow_id: int,
    ) -> Optional[Workflow]:
        """Set deleted_at to current UTC time; returns None if not found or already deleted."""
        workflow = await WorkflowService.get_workflow_by_id(db, workflow_id)
        if workflow is None:
            return None
        workflow.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(workflow)
        return workflow