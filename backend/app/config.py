import os
from pydantic_settings import BaseSettings
from typing import List
from app.secrets import get_secret


class Settings(BaseSettings):
    """Application settings from environment variables or SQLite secrets store"""

    # App config
    DEBUG: bool = False
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    SECRET_KEY: str = "your-super-secret-jwt-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost/taskflow"
    DB_ECHO: bool = False

    # Rate limiting
    RATE_LIMIT_TIMES: int = 100
    RATE_LIMIT_SECONDS: int = 60

    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Override with secrets from SQLite if available (but don't override explicit env vars)
        # Only override if the value is still the default placeholder
        if self.SECRET_KEY == "your-super-secret-jwt-key-change-in-production":
            secret_from_db = get_secret("SECRET_KEY")
            if secret_from_db:
                self.SECRET_KEY = secret_from_db

        if self.DATABASE_URL == "postgresql+asyncpg://postgres:password@localhost/taskflow":
            db_from_db = get_secret("DATABASE_URL")
            if db_from_db:
                self.DATABASE_URL = db_from_db


settings = Settings()