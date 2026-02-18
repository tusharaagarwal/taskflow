"""
Start the Workflow Orchestrator API (SQS assembler completion runs in-process).

The assembler completion consumer runs inside the API process (FastAPI lifespan).
This script starts the API so the in-process consumer is active.

Usage (from workflow_orchestrator/server):
  poetry run python scripts/run_assembler_completion_consumer.py

Requires:
  - AWS credentials when messaging_enabled is True
  - Config: ORCHESTRATOR_API_BASE_URL for report-tracker calls (default from host/port)
"""
import logging
import sys
from pathlib import Path

# Ensure server root is on path so "app" resolves
_server_root = Path(__file__).resolve().parent.parent
if str(_server_root) not in sys.path:
    sys.path.insert(0, str(_server_root))


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)


def main() -> None:
    _configure_logging()
    logger = logging.getLogger(__name__)

    from app.config.config import settings
    from app.main import app
    import uvicorn

    if not settings.messaging_enabled:
        logger.warning("Messaging is disabled. SQS consumer will not start; API will still run.")

    host = getattr(settings, "host", "0.0.0.0")
    port = getattr(settings, "port", 8003)

    logger.info(
        "Starting Workflow Orchestrator API (assembler completion SQS consumer runs in-process). "
        "Host: %s, port: %s. Ctrl+C to stop.",
        host,
        port,
    )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
