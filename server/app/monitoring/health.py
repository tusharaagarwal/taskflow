"""
Health monitoring endpoints for the Workflow Orchestrator API
"""
import psutil
import time
from typing import Dict, Any
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text
from app.logger import logger
from app.db.database import engine

router = APIRouter()


async def check_database(db_engine: AsyncEngine):
    """Check database connectivity"""
    try:
        async with db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "Database is healthy"
    except Exception as e:
        return False, str(e)


def get_system_health():
    """Get system health metrics"""
    # Import here to avoid circular import
    from app.main import start_time
    
    cpu = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    uptime = time.time() - start_time

    system_health = {
        "cpu_usage": f"{cpu}%",
        "memory_usage": f"{memory.percent}%",
        "disk_usage": f"{disk.percent}%",
        "uptime_seconds": int(uptime),
    }

    healthy = cpu < 90 and memory.percent < 90 and disk.percent < 90

    return healthy, system_health


@router.get("/_health", response_model=Dict[str, Any])
async def basic_health_check():
    """
    Comprehensive health check endpoint for load balancers and monitoring systems
    Checks database connectivity and system health
    """
    results = {}

    # Database
    db_ok, db_msg = await check_database(engine)
    results["database"] = {"healthy": db_ok, "message": db_msg}

    # System Health
    sys_ok, sys_info = get_system_health()
    results["system"] = {"healthy": sys_ok, "metrics": sys_info}

    # Overall status
    overall = all(service["healthy"] for service in results.values())

    return {
        "status": "healthy" if overall else "unhealthy",
        "services": results
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness check endpoint - indicates if the service is ready to accept traffic
    Kubernetes/ECS readiness probe
    """
    logger.debug("Readiness check requested")
    
    # Check critical dependencies
    db_ok, db_msg = await check_database(engine)
    
    if not db_ok:
        return {
            "status": "not_ready",
            "reason": "Database not available",
            "timestamp": time.time()
        }
    
    return {
        "status": "ready",
        "timestamp": time.time(),
        "service": "workflow-orchestrator"
    }


@router.get("/live")
async def liveness_check():
    """
    Liveness check endpoint - indicates if the service is alive
    Kubernetes/ECS liveness probe
    """
    logger.debug("Liveness check requested")
    
    return {
        "status": "alive",
        "timestamp": time.time(),
        "service": "workflow-orchestrator"
    }

