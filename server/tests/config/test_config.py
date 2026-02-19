"""Tests for app.config.config (validate_settings and env helpers)."""
import importlib
import os
import pytest
from unittest.mock import patch

from app.config.config import validate_settings, settings


class TestConfigEnvHelpers:
    """Test _env_bool, _env_int, _env_list to cover config module branches."""

    def test_env_bool_returns_true_for_truthy_values(self):
        from app.config.config import _env_bool
        with patch.dict(os.environ, {"TEST_ENV_BOOL": "true"}, clear=False):
            assert _env_bool("TEST_ENV_BOOL", False) is True
        with patch.dict(os.environ, {"TEST_ENV_BOOL": "1"}, clear=False):
            assert _env_bool("TEST_ENV_BOOL", False) is True

    def test_env_int_returns_default_on_invalid_value(self):
        from app.config.config import _env_int
        with patch.dict(os.environ, {"TEST_ENV_INT": "not_a_number"}, clear=False):
            assert _env_int("TEST_ENV_INT", 42) == 42

    def test_env_list_returns_split_list_when_non_empty(self):
        from app.config.config import _env_list
        with patch.dict(os.environ, {"TEST_ENV_LIST": "a, b , c"}, clear=False):
            assert _env_list("TEST_ENV_LIST", None) == ["a", "b", "c"]


class TestValidateSettings:
    """Test validate_settings branches."""

    def test_invalid_environment_raises(self):
        with patch.object(settings, "environment", "invalid_env"):
            with pytest.raises(ValueError, match="Invalid environment"):
                validate_settings()

    def test_invalid_port_low_raises(self):
        with patch.object(settings, "environment", "dev"), patch.object(
            settings, "port", 0
        ):
            with pytest.raises(ValueError, match="Invalid port"):
                validate_settings()

    def test_invalid_port_high_raises(self):
        with patch.object(settings, "environment", "dev"), patch.object(
            settings, "port", 70000
        ):
            with pytest.raises(ValueError, match="Invalid port"):
                validate_settings()

    def test_invalid_pagination_raises(self):
        with patch.object(settings, "environment", "dev"), patch.object(
            settings, "port", 8000
        ), patch.object(settings, "default_page_size", 0):
            with pytest.raises(ValueError, match="Invalid pagination"):
                validate_settings()

    def test_invalid_access_token_expire_raises(self):
        with patch.object(settings, "environment", "dev"), patch.object(
            settings, "port", 8000
        ), patch.object(settings, "default_page_size", 10), patch.object(
            settings, "max_page_size", 100
        ), patch.object(settings, "access_token_expire_minutes", 0):
            with pytest.raises(ValueError, match="Access token"):
                validate_settings()

    def test_invalid_max_file_size_raises(self):
        with patch.object(settings, "environment", "dev"), patch.object(
            settings, "port", 8000
        ), patch.object(settings, "default_page_size", 10), patch.object(
            settings, "max_page_size", 100
        ), patch.object(settings, "access_token_expire_minutes", 30), patch.object(
            settings, "max_file_size", -1
        ):
            with pytest.raises(ValueError, match="Max file size"):
                validate_settings()

    def test_valid_settings_no_raise(self):
        with patch.object(settings, "environment", "dev"), patch.object(
            settings, "port", 8000
        ), patch.object(settings, "default_page_size", 10), patch.object(
            settings, "max_page_size", 100
        ), patch.object(settings, "access_token_expire_minutes", 30), patch.object(
            settings, "max_file_size", 1024
        ):
            validate_settings()


class TestOrchestratorBaseUrl:
    """Test _orchestrator_base_url_from_server for placeholder hosts."""

    def test_placeholder_host_0_0_0_0_uses_127_0_0_1(self):
        from app.config.config import _orchestrator_base_url_from_server
        assert _orchestrator_base_url_from_server("0.0.0.0", 8003) == "http://127.0.0.1:8003"

    def test_placeholder_host_double_colon_uses_127_0_0_1(self):
        from app.config.config import _orchestrator_base_url_from_server
        assert _orchestrator_base_url_from_server("::", 8003) == "http://127.0.0.1:8003"

    def test_normal_host_unchanged(self):
        from app.config.config import _orchestrator_base_url_from_server
        assert _orchestrator_base_url_from_server("localhost", 8000) == "http://localhost:8000"


class TestSettingsAwsLoadFailure:
    """Test Settings fallback when AWS messaging config load raises."""

    def test_aws_config_load_failure_sets_messaging_enabled_false(self):
        """When get_aws_messaging_config raises, Settings uses fallback with messaging_enabled=False."""
        import app.config.config as config_mod
        with patch("config_loader.config.get_aws_messaging_config", side_effect=Exception("test load failure")):
            importlib.reload(config_mod)
        try:
            assert config_mod.settings.messaging_enabled is False
            assert config_mod.settings.aws_region == "ap-south-1"
            assert config_mod.settings.assembler_task_queue_name == "orchestrator-to-assembler"
        finally:
            # Restore normal config so other tests see correct settings
            importlib.reload(config_mod)
