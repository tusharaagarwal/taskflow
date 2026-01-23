from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config_loader import config

# Get database configuration from config manager
db_config = config.get_database_config()
DATABASE_URL = config.get_database_url()

# Individual database configuration variables (for backward compatibility)
POSTGRES_HOST = db_config["host"]
POSTGRES_PORT = db_config["port"]
POSTGRES_DB = db_config["db"]
POSTGRES_USER = db_config["user"]
POSTGRES_PASSWORD = db_config["password"]

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create async session
AsyncSessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

# Add dependency function for FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

