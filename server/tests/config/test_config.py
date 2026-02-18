"""Tests for app.config.config (validate_settings)."""
import pytest
from unittest.mock import patch

from app.config.config import validate_settings, settings


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
