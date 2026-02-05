# Configuration settings for the FastAPI application (no pydantic-settings)
import os
from typing import List, Optional

# Load .env if present (python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_list(key: str, default: Optional[List[str]] = None) -> List[str]:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default or []
    return [x.strip() for x in raw.split(",") if x.strip()]


class Settings:
    """Application settings loaded from environment variables (no pydantic-settings)."""

    def __init__(self) -> None:
        # Application
        self.app_name: str = _env("APP_NAME", "Workflow Orchestrator API")
        self.app_version: str = _env("APP_VERSION", "2.0.0")
        self.debug: bool = _env_bool("DEBUG", True)
        self.environment: str = _env("ENVIRONMENT", "development")

        # Server
        self.host: str = _env("HOST", "0.0.0.0")
        self.port: int = _env_int("PORT", 8000)
        self.reload: bool = _env_bool("RELOAD", True)

        # Database
        self.database_url: str = _env(
            "DATABASE_URL", "sqlite:///./workflow_orchestrator.db"
        )
        self.database_echo: bool = _env_bool("DATABASE_ECHO", False)
        self.database_pool_size: int = _env_int("DATABASE_POOL_SIZE", 5)
        self.database_max_overflow: int = _env_int("DATABASE_MAX_OVERFLOW", 10)

        # CORS
        self.cors_origins: List[str] = _env_list(
            "CORS_ORIGINS",
            ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8080", "http://127.0.0.1:8080"],
        )
        self.cors_allow_credentials: bool = _env_bool("CORS_ALLOW_CREDENTIALS", True)
        self.cors_allow_methods: List[str] = _env_list("CORS_ALLOW_METHODS", ["*"])
        self.cors_allow_headers: List[str] = _env_list("CORS_ALLOW_HEADERS", ["*"])

        # Security
        self.secret_key: str = _env(
            "SECRET_KEY", "your-secret-key-change-in-production"
        )
        self.access_token_expire_minutes: int = _env_int(
            "ACCESS_TOKEN_EXPIRE_MINUTES", 30
        )
        self.refresh_token_expire_days: int = _env_int("REFRESH_TOKEN_EXPIRE_DAYS", 7)
        self.algorithm: str = _env("ALGORITHM", "HS256")

        # Logging
        self.log_level: str = _env("LOG_LEVEL", "INFO")
        self.log_file: str = _env("LOG_FILE", "app.log")
        self.log_format: str = _env(
            "LOG_FORMAT",
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Pagination
        self.default_page_size: int = _env_int("DEFAULT_PAGE_SIZE", 20)
        self.max_page_size: int = _env_int("MAX_PAGE_SIZE", 100)

        # API
        self.api_prefix: str = _env("API_PREFIX", "/api/v1")
        self.docs_url: str = _env("DOCS_URL", "/docs")
        self.redoc_url: str = _env("REDOC_URL", "/redoc")
        self.openapi_url: str = _env("OPENAPI_URL", "/openapi.json")

        # Rate limiting
        self.rate_limit_enabled: bool = _env_bool("RATE_LIMIT_ENABLED", False)
        self.rate_limit_requests: int = _env_int("RATE_LIMIT_REQUESTS", 100)
        self.rate_limit_window: int = _env_int("RATE_LIMIT_WINDOW", 60)

        # Cache
        self.cache_enabled: bool = _env_bool("CACHE_ENABLED", False)
        self.cache_ttl: int = _env_int("CACHE_TTL", 300)
        self.cache_backend: str = _env("CACHE_BACKEND", "memory")
        self.redis_url: str = _env("REDIS_URL", "redis://localhost:6379")

        # Abbreviation cache
        self.abbreviation_cache_enabled: bool = _env_bool(
            "ABBREVIATION_CACHE_ENABLED", True
        )
        self.abbreviation_cache_ttl: int = _env_int(
            "ABBREVIATION_CACHE_TTL", 3600
        )
        self.abbreviation_cache_max_size: int = _env_int(
            "ABBREVIATION_CACHE_MAX_SIZE", 1000
        )
        self.abbreviation_raise_on_not_found: bool = _env_bool(
            "ABBREVIATION_RAISE_ON_NOT_FOUND", True
        )
        self.abbreviation_default: str = _env("ABBREVIATION_DEFAULT", "DOC")

        # Email
        self.email_enabled: bool = _env_bool("EMAIL_ENABLED", False)
        self.smtp_host: str = _env("SMTP_HOST", "localhost")
        self.smtp_port: int = _env_int("SMTP_PORT", 587)
        self.smtp_username: str = _env("SMTP_USERNAME", "")
        self.smtp_password: str = _env("SMTP_PASSWORD", "")
        self.smtp_use_tls: bool = _env_bool("SMTP_USE_TLS", True)

        # File upload
        self.max_file_size: int = _env_int("MAX_FILE_SIZE", 10 * 1024 * 1024)
        self.allowed_file_types: List[str] = _env_list(
            "ALLOWED_FILE_TYPES",
            ["image/jpeg", "image/png", "application/pdf", "text/plain"],
        )
        self.upload_path: str = _env("UPLOAD_PATH", "./uploads")

        # Monitoring
        self.metrics_enabled: bool = _env_bool("METRICS_ENABLED", True)
        self.health_check_interval: int = _env_int("HEALTH_CHECK_INTERVAL", 30)

        # Workflow
        self.max_concurrent_workflows: int = _env_int(
            "MAX_CONCURRENT_WORKFLOWS", 10
        )
        self.workflow_timeout: int = _env_int("WORKFLOW_TIMEOUT", 3600)
        self.retry_attempts: int = _env_int("RETRY_ATTEMPTS", 3)
        self.retry_delay: int = _env_int("RETRY_DELAY", 5)

        # Messaging (used by messaging router and AWS service)
        self.messaging_enabled: bool = _env_bool("MESSAGING_ENABLED", False)
        self.aws_region: str = _env("AWS_REGION", "ap-south-2")
        self.aws_access_key_id: Optional[str] = _env("AWS_ACCESS_KEY_ID") or None
        self.aws_secret_access_key: Optional[str] = _env("AWS_SECRET_ACCESS_KEY") or None
        self.aws_session_token: Optional[str] = _env("AWS_SESSION_TOKEN") or None
        self.assembler_queue_name: str = _env(
            "ASSEMBLER_QUEUE_NAME", "CreditOpinionAssembler"
        )
        self.endpoint_queue_name: str = _env(
            "ENDPOINT_QUEUE_NAME", "WorkflowOrchestratorEndpoint"
        )
        self.report_update_topic_name: str = _env(
            "REPORT_UPDATE_TOPIC_NAME", "workflow_orchestrator_updates"
        )


# Single instance
settings = Settings()


def validate_settings() -> None:
    """Validate configuration settings."""
    if settings.environment not in ["dev", "qa", "pre_prod", "prod", "development"]:
        raise ValueError(f"Invalid environment: {settings.environment}")

    if settings.port < 1 or settings.port > 65535:
        raise ValueError(f"Invalid port: {settings.port}")

    if settings.default_page_size < 1 or settings.default_page_size > settings.max_page_size:
        raise ValueError("Invalid pagination settings")

    if settings.access_token_expire_minutes < 1:
        raise ValueError("Access token expiration must be positive")

    if settings.max_file_size < 0:
        raise ValueError("Max file size must be non-negative")


# Validate on import (optional: skip in tests by setting SKIP_CONFIG_VALIDATION=1)
if not _env_bool("SKIP_CONFIG_VALIDATION", False):
    validate_settings()


__all__ = ["settings", "Settings", "validate_settings"]
