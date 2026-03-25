from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database import get_db
from app.models import Task, TaskStatus
from app.schemas import TaskCreate, TaskUpdate, TaskResponse
from app.routers.auth import get_current_user
from app.models import User
import logging

router = APIRouter(tags=["Tasks"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    status_filter: Optional[TaskStatus] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for current user with optional status filter"""
    query = select(Task).where(Task.owner_id == current_user.id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new task using ORM like user update does"""
    try:
        print(f"=== CREATING TASK ===", flush=True)
        print(f"User ID: {current_user.id}", flush=True)
        print(f"Title: {task_data.title}", flush=True)
        print(f"Status: {task_data.status}", flush=True)
        print(f"Priority: {task_data.priority}", flush=True)

        # Create task object like user update does
        task = Task(
            title=task_data.title,
            description=task_data.description or None,
            status=task_data.status,
            priority=task_data.priority,
            owner_id=current_user.id
        )

        print(f"Task object created: {task}", flush=True)

        db.add(task)
        await db.commit()
        await db.refresh(task)

        print(f"Task created successfully: {task.id}", flush=True)
        return task
    except Exception as e:
        print(f"=== ERROR CREATING TASK ===", flush=True)
        print(f"Error type: {type(e).__name__}", flush=True)
        print(f"Error message: {str(e)}", flush=True)
        import traceback
        print(f"Traceback:\n{traceback.format_exc()}", flush=True)

        logger.error(f"Create task error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific task"""
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.owner_id == current_user.id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a task"""
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.owner_id == current_user.id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = task_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task"""
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.owner_id == current_user.id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await db.delete(task)
    await db.commit()
    return None