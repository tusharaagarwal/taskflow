"""
Tests for app.utils.security.sanitize_log_input.
"""

import pytest

from app.utils.security import sanitize_log_input


def test_sanitize_log_input_safe_string_unchanged():
    """Safe strings are returned unchanged."""
    assert sanitize_log_input("hello") == "hello"
    assert sanitize_log_input("normal text 123") == "normal text 123"
    assert sanitize_log_input("no-newlines") == "no-newlines"


def test_sanitize_log_input_newline_replaced():
    """Newline characters are replaced with literal \\n."""
    assert sanitize_log_input("a\nb") == "a\\nb"
    assert sanitize_log_input("\n\n") == "\\n\\n"


def test_sanitize_log_input_carriage_return_replaced():
    """Carriage return characters are replaced with literal \\r."""
    assert sanitize_log_input("a\rb") == "a\\rb"
    assert sanitize_log_input("\r\n") == "\\r\\n"


def test_sanitize_log_input_both_newline_and_cr_replaced():
    """Both \\n and \\r are sanitized."""
    assert sanitize_log_input("line1\r\nline2") == "line1\\r\\nline2"


def test_sanitize_log_input_empty_string():
    """Empty string returns empty string."""
    assert sanitize_log_input("") == ""


def test_sanitize_log_input_non_string_converted_to_string():
    """Non-string input is converted to string via str()."""
    assert sanitize_log_input(None) == "None"
    assert sanitize_log_input(42) == "42"
    assert sanitize_log_input(3.14) == "3.14"
    assert sanitize_log_input(True) == "True"


def test_sanitize_log_input_injection_like_pattern_sanitized():
    """Input that could look like log injection (newlines) is sanitized."""
    payload = "user\n[CRITICAL] fake log line"
    assert "\\n" in sanitize_log_input(payload)
    assert "\n" not in sanitize_log_input(payload)
