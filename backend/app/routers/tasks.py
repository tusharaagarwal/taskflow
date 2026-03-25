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
    """Create a new task using raw SQL"""
    try:
        # Use raw SQL INSERT
        result = await db.execute(
            text("""
                INSERT INTO tasks (title, description, status, priority, owner_id, created_at, updated_at) 
                VALUES (:title, :desc, :status, :priority, :owner_id, NOW(), NOW())
                RETURNING id, title, description, status, priority, owner_id, created_at, updated_at
            """),
            {
                "title": task_data.title,
                "desc": task_data.description,
                "status": task_data.status,
                "priority": task_data.priority,
                "owner_id": current_user.id
            }
        )
        row = result.fetchone()
        await db.commit()
        
        return {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "status": row[3],
            "priority": row[4],
            "owner_id": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "due_date": None
        }
    except Exception as e:
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