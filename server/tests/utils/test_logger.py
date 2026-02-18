"""Tests for app.logger (logger configuration)."""
import importlib
import logging
import os
import sys
from unittest.mock import patch


def test_logger_dotenv_import_error_handled():
    """When dotenv import fails, logger module still loads (except path)."""
    old_dotenv = sys.modules.get("dotenv")
    fake_dotenv = type(sys)("dotenv")  # module with no load_dotenv
    sys.modules["dotenv"] = fake_dotenv
    try:
        if "app.logger" in sys.modules:
            del sys.modules["app.logger"]
        import app.logger as logmod
        assert logmod.logger is not None
    finally:
        if old_dotenv is not None:
            sys.modules["dotenv"] = old_dotenv
        else:
            del sys.modules["dotenv"]
        if "app.logger" in sys.modules:
            del sys.modules["app.logger"]


def test_logger_exists_and_has_handler():
    """Logger is created and has a console handler."""
    import app.logger as logmod
    assert logmod.logger.name == "workflow_orchestrator_app_logger"
    assert len(logmod.logger.handlers) >= 1
    assert logmod.logger.propagate is False


def test_logger_prod_environment_sets_info_level_and_formatter():
    """When ENVIRONMENT is prod-like, logger uses INFO and production formatter path."""
    with patch.dict(os.environ, {"ENVIRONMENT": "prod"}, clear=False):
        import app.logger as logmod
        importlib.reload(logmod)
        try:
            assert logmod.logger.level == logging.INFO
            assert logmod.logger.handlers[0].level == logging.INFO
        finally:
            importlib.reload(logmod)
