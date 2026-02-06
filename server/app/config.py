# Configuration settings for the FastAPI application
import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings"""
    
    # Application settings
    app_name: str = Field(default="Workflow Orchestrator API", description="Application name")
    app_version: str = Field(default="2.0.0", description="Application version")
    debug: bool = Field(default=True, description="Debug mode")
    environment: str = Field(default="development", description="Environment (development/production)")
    
    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    reload: bool = Field(default=True, description="Auto-reload on code changes")
    
    # Database settings
    database_url: str = Field(
        default="sqlite:///./workflow_orchestrator.db", 
        description="Database connection URL"
    )
    database_echo: bool = Field(default=False, description="Echo SQL queries")
    database_pool_size: int = Field(default=5, description="Database connection pool size")
    database_max_overflow: int = Field(default=10, description="Database max overflow connections")
    
    # CORS settings
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8080",
            "http://127.0.0.1:8080"
        ],
        description="Allowed CORS origins"
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow CORS credentials")
    cors_allow_methods: List[str] = Field(default=["*"], description="Allowed CORS methods")
    cors_allow_headers: List[str] = Field(default=["*"], description="Allowed CORS headers")
    
    # Security settings
    secret_key: str = Field(
        default="your-secret-key-change-in-production", 
        description="Secret key for JWT tokens"
    )
    access_token_expire_minutes: int = Field(default=30, description="Access token expiration in minutes")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token expiration in days")
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    
    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: str = Field(default="app.log", description="Log file path")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format"
    )
    
    # Pagination settings
    default_page_size: int = Field(default=20, description="Default page size for pagination")
    max_page_size: int = Field(default=100, description="Maximum page size for pagination")
    
    # API settings
    api_prefix: str = Field(default="/api/v1", description="API prefix")
    docs_url: str = Field(default="/docs", description="Swagger docs URL")
    redoc_url: str = Field(default="/redoc", description="ReDoc URL")
    openapi_url: str = Field(default="/openapi.json", description="OpenAPI JSON URL")
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=False, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Rate limit requests per minute")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")
    
    # Cache settings
    cache_enabled: bool = Field(default=False, description="Enable caching")
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")
    cache_backend: str = Field(default="memory", description="Cache backend (memory/redis)")
    redis_url: str = Field(default="redis://localhost:6379", description="Redis URL")
    
    # Email settings
    email_enabled: bool = Field(default=False, description="Enable email notifications")
    smtp_host: str = Field(default="localhost", description="SMTP host")
    smtp_port: int = Field(default=587, description="SMTP port")
    smtp_username: str = Field(default="", description="SMTP username")
    smtp_password: str = Field(default="", description="SMTP password")
    smtp_use_tls: bool = Field(default=True, description="Use TLS for SMTP")
    
    # File upload settings
    max_file_size: int = Field(default=10 * 1024 * 1024, description="Max file size in bytes (10MB)")
    allowed_file_types: List[str] = Field(
        default=["image/jpeg", "image/png", "application/pdf", "text/plain"],
        description="Allowed file types"
    )
    upload_path: str = Field(default="./uploads", description="File upload path")
    
    # Monitoring settings
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
    
    # Workflow settings
    max_concurrent_workflows: int = Field(default=10, description="Max concurrent workflows")
    workflow_timeout: int = Field(default=3600, description="Workflow timeout in seconds")
    retry_attempts: int = Field(default=3, description="Number of retry attempts")
    retry_delay: int = Field(default=5, description="Retry delay in seconds")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        validate_assignment = True

# Create settings instance
settings = Settings()

# Environment-specific overrides
if settings.environment == "production":
    settings.debug = False
    settings.log_level = "WARNING"
    settings.reload = False
    settings.cors_origins = [
        "https://yourdomain.com",
        "https://www.yourdomain.com"
    ]
    settings.database_echo = False
    settings.rate_limit_enabled = True
    settings.cache_enabled = True

# Development-specific overrides
if settings.environment == "development":
    settings.debug = True
    settings.log_level = "DEBUG"
    settings.reload = True
    settings.database_echo = True
    settings.rate_limit_enabled = False
    settings.cache_enabled = False

# Test-specific overrides
if settings.environment == "testing":
    settings.debug = True
    settings.log_level = "DEBUG"
    settings.database_url = "sqlite:///./test_workflow_orchestrator.db"
    settings.database_echo = False
    settings.rate_limit_enabled = False
    settings.cache_enabled = False

# Validation
def validate_settings():
    """Validate configuration settings"""
    if settings.environment not in ["development", "production", "testing"]:
        raise ValueError(f"Invalid environment: {settings.environment}")
    
    if settings.port < 1 or settings.port > 65535:
        raise ValueError(f"Invalid port: {settings.port}")
    
    if settings.default_page_size < 1 or settings.default_page_size > settings.max_page_size:
        raise ValueError("Invalid pagination settings")
    
    if settings.access_token_expire_minutes < 1:
        raise ValueError("Access token expiration must be positive")
    
    if settings.max_file_size < 0:
        raise ValueError("Max file size must be non-negative")

# Validate settings on import
validate_settings()

# Export commonly used settings
__all__ = ["settings"]