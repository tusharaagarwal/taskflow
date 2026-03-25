import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
from sqlalchemy.exc import SQLAlchemyError

# Set up logging with DEBUG level for detailed output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from app.config import settings
from app.database import engine, Base
from app.routers import auth, tasks, users
from app.middleware.rate_limit import limiter, setup_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events"""
    # Startup
    logger.info("🚀 TaskFlow API starting...")
    # Create tables if they don't exist (preserve existing data)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables ready")
    yield
    # Shutdown
    logger.info("🛑 TaskFlow API shutting down...")
    await engine.dispose()


app = FastAPI(
    title="TaskFlow API",
    description="A production-ready task management API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Setup rate limiting
setup_middleware(app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"General Error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "taskflow-api"
    }

# Test database connection
@app.get("/test-db", tags=["Debug"])
async def test_db(db: AsyncSession = Depends(get_db)):
    """Test database connection"""
    try:
        result = await db.execute("SELECT 1 as test")
        row = result.fetchone()
        return {"db_status": "ok", "test_result": row[0]}
    except Exception as e:
        return {"db_status": "error", "error": str(e)}


# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])

print("=== ALL ROUTERS LOADED ===", flush=True)


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to TaskFlow API",
        "docs": "/docs",
        "version": app.version
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )