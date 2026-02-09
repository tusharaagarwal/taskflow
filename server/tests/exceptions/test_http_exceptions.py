"""
Unit tests for app.exceptions.http_exceptions.
"""
import pytest
from fastapi import HTTPException

from app.exceptions.http_exceptions import (
    NotFoundException,
    ForbiddenException,
    ExternalServiceException,
    UnprocessableEntityException,
)


class TestNotFoundException:
    """Tests for NotFoundException."""

    def test_default_detail(self):
        """Default detail is 'Resource not found'."""
        exc = NotFoundException()
        assert exc.status_code == 404
        assert exc.detail == "Resource not found"

    def test_custom_detail(self):
        """Custom detail is preserved."""
        exc = NotFoundException(detail="User 123 not found")
        assert exc.status_code == 404
        assert exc.detail == "User 123 not found"

    def test_with_headers(self):
        """Optional headers are passed to HTTPException."""
        exc = NotFoundException(headers={"X-Custom": "value"})
        assert exc.headers == {"X-Custom": "value"}

    def test_inherits_http_exception(self):
        """NotFoundException is an HTTPException."""
        exc = NotFoundException()
        assert isinstance(exc, HTTPException)


class TestForbiddenException:
    """Tests for ForbiddenException."""

    def test_default_detail(self):
        exc = ForbiddenException()
        assert exc.status_code == 403
        assert exc.detail == "Forbidden"

    def test_custom_detail(self):
        exc = ForbiddenException(detail="Access denied")
        assert exc.status_code == 403
        assert exc.detail == "Access denied"


class TestExternalServiceException:
    """Tests for ExternalServiceException."""

    def test_default_detail(self):
        exc = ExternalServiceException()
        assert exc.status_code == 500
        assert exc.detail == "External service error"

    def test_custom_detail(self):
        exc = ExternalServiceException(detail="CPM API timeout")
        assert exc.status_code == 500
        assert exc.detail == "CPM API timeout"


class TestUnprocessableEntityException:
    """Tests for UnprocessableEntityException."""

    def test_default_detail(self):
        exc = UnprocessableEntityException()
        assert exc.status_code == 422
        assert exc.detail == "Unprocessable Entity"

    def test_custom_detail(self):
        exc = UnprocessableEntityException(detail="Invalid transition path")
        assert exc.status_code == 422
        assert exc.detail == "Invalid transition path"
