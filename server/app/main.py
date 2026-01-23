# Simplified FastAPI application that works with current setup
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import time
from app.routers.v1 import report_tracker, root, cpm_mock
from app.monitoring import health
from app.logger import logger
from app.middleware import RequestResponseMiddleware, SecurityHeadersMiddleware

# Pydantic models
class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = None

class WorkflowCreate(WorkflowBase):
    pass

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class WorkflowResponse(WorkflowBase):
    id: int
    status: str
    created_at: str

# In-memory storage
workflows_db = []
workflow_counter = 1

# Track application uptime
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info("Application starting up", extra={"event": "startup"})
    yield
    logger.info("Application shutting down", extra={"event": "shutdown"})


# Create FastAPI instance
app = FastAPI(
    title="Workflow Orchestrator API",
    description="A FastAPI application for workflow orchestration",
    version="2.0.0",
    lifespan=lifespan
)

# Add Security Headers Middleware (first)
app.add_middleware(SecurityHeadersMiddleware)

# Add Request/Response Logging Middleware
app.add_middleware(RequestResponseMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(root.router, tags=["root"])
app.include_router(health.router, prefix="/v1/health", tags=["health"])
app.include_router(report_tracker.router, prefix="/v1")
app.include_router(cpm_mock.router, prefix="/v1")  # TEMP MOCK: CPM API

# Workflow endpoints
@app.get("/workflows", response_model=List[WorkflowResponse])
async def get_workflows():
    """Get all workflows"""
    logger.info(f"Fetching all workflows - Count: {len(workflows_db)}")
    return workflows_db

@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: int):
    """Get a specific workflow by ID"""
    logger.info(f"Fetching workflow with ID: {workflow_id}")
    workflow = next((w for w in workflows_db if w["id"] == workflow_id), None)
    if not workflow:
        logger.warning(f"Workflow not found - ID: {workflow_id}")
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow

@app.post("/workflows", response_model=WorkflowResponse)
async def create_workflow(workflow: WorkflowCreate):
    """Create a new workflow"""
    global workflow_counter
    logger.info(f"Creating new workflow - Name: {workflow.name}")
    new_workflow = {
        "id": workflow_counter,
        "name": workflow.name,
        "description": workflow.description,
        "status": "pending",
        "created_at": "2024-01-01T00:00:00Z"
    }
    workflows_db.append(new_workflow)
    logger.info(f"Workflow created successfully - ID: {workflow_counter}, Name: {workflow.name}")
    workflow_counter += 1
    return new_workflow

@app.put("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: int, workflow_update: WorkflowUpdate):
    """Update an existing workflow"""
    logger.info(f"Updating workflow - ID: {workflow_id}")
    workflow = next((w for w in workflows_db if w["id"] == workflow_id), None)
    if not workflow:
        logger.warning(f"Workflow not found for update - ID: {workflow_id}")
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Update fields if provided
    updated_fields = []
    if workflow_update.name is not None:
        workflow["name"] = workflow_update.name
        updated_fields.append("name")
    if workflow_update.description is not None:
        workflow["description"] = workflow_update.description
        updated_fields.append("description")
    if workflow_update.status is not None:
        workflow["status"] = workflow_update.status
        updated_fields.append("status")
    
    logger.info(f"Workflow updated successfully - ID: {workflow_id}, Updated fields: {', '.join(updated_fields)}")
    return workflow

@app.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int):
    """Delete a workflow"""
    global workflows_db
    logger.info(f"Deleting workflow - ID: {workflow_id}")
    workflow = next((w for w in workflows_db if w["id"] == workflow_id), None)
    if not workflow:
        logger.warning(f"Workflow not found for deletion - ID: {workflow_id}")
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    workflows_db = [w for w in workflows_db if w["id"] != workflow_id]
    logger.info(f"Workflow deleted successfully - ID: {workflow_id}")
    return {"message": "Workflow deleted successfully"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)