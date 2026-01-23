import logging
import os

try:
    # Optional: load .env if present; safe if python-dotenv is installed
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()  # no-op if .env is missing
except Exception:
    pass

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev").lower()

# Create named logger used across the app
logger = logging.getLogger("workflow_orchestrator_app_logger")

# Ensure no duplicate handlers if module is reloaded
for existing_handler in list(logger.handlers):
    logger.removeHandler(existing_handler)

# Level policy: prod/pre_prod -> INFO; dev -> DEBUG
if ENVIRONMENT in {"prod", "production", "pre_prod", "staging"}:
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.DEBUG)

# Handlers
console_handler = logging.StreamHandler()

if ENVIRONMENT in {"prod", "production", "pre_prod", "staging"}:
    # In production-like environments, emit JSON to stdout for Logstash ingestion
    try:
        from pythonjsonlogger import jsonlogger  # type: ignore

        json_format = (
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "%(module)s %(filename)s %(lineno)d %(funcName)s %(process)d %(thread)d"
        )
        json_formatter = jsonlogger.JsonFormatter(json_format)
        console_handler.setFormatter(json_formatter)
    except Exception:
        # Fallback to a plain formatter if dependency missing, still structured-friendly
        fallback = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(fallback)
    console_handler.setLevel(logging.INFO)
else:
    # Developer-friendly console formatting in non-prod
    dev_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(dev_formatter)
    console_handler.setLevel(logging.DEBUG)

# In prod we do console-only so Logstash picks up stdout
logger.addHandler(console_handler)

# Avoid propagating to root to prevent duplicate logs if uvicorn config also logs
logger.propagate = False