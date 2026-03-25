from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from app.config import settings
import logging

# Async engine - use Railway's DATABASE_URL as-is
_db_url = settings.DATABASE_URL
logger = logging.getLogger(__name__)
logger.info(f"DATABASE_URL: {_db_url}")

engine = create_async_engine(
    _db_url,
    echo=settings.DB_ECHO,
    poolclass=NullPool,
)

# Async session factory
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Base for models
Base = declarative_base()


async def get_db():
    """Dependency for database session"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.close()