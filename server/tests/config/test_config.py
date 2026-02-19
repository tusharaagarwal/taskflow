"""Tests for app.config.config (validate_settings and env helpers)."""
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
