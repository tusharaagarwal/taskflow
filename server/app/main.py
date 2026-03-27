# Simplified FastAPI application that works with current setup
import time
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.v1 import abbreviation, report_tracker, root, cpm_mock, messaging, runtime_app_config, workflow
from app.monitoring import health
from app.logger import logger
from app.middleware import RequestResponseMiddleware, SecurityHeadersMiddleware
from app.config.config import settings
from app.db.database import AsyncSessionLocal
from app.services.runtime_app_config_service import RuntimeAppConfigService
from app.services.sqs_consumer import sqs_consumer

# Track application uptime
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events.

    SQS assembler completion consumer runs in-process (app.services.sqs_consumer),
    started here when messaging_enabled is True.
    """
    logger.info("Application starting up", extra={"event": "startup"})

    try:
        async with AsyncSessionLocal() as session:
            await RuntimeAppConfigService.ensure_singleton(session)
            await session.commit()
        logger.info("Application runtime config singleton row ensured")
    except Exception as e:
        logger.error("Failed to ensure application runtime config row: %s", e, exc_info=True)

    if settings.messaging_enabled:
        try:
            await sqs_consumer.start()
            logger.info("SQS consumer started successfully")
        except Exception as e:
            logger.error("Failed to start SQS consumer: %s", e)

    yield

    if settings.messaging_enabled:
        try:
            await sqs_consumer.stop()
            logger.info("SQS consumer stopped")
        except Exception as e:
            logger.error("Error stopping SQS consumer: %s", e)

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
app.include_router(abbreviation.router, prefix="/v1")
app.include_router(report_tracker.router, prefix="/v1")
app.include_router(cpm_mock.router, prefix="/v1")  # TEMP MOCK: CPM API
app.include_router(messaging.router, prefix="/v1", tags=["messaging"])
app.include_router(runtime_app_config.router, prefix="/v1")
app.include_router(workflow.router, prefix="/api/v1")

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
