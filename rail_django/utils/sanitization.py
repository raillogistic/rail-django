"""
Sanitization utilities for Rail Django.

This module provides functions for sanitizing user input, filenames,
queries, and other data to prevent security issues.
"""

import html
import re
from typing import Any, Dict


# Characters allowed in filenames
FILENAME_SAFE_PATTERN = re.compile(r"[^\w\s\-_\.]")
FILENAME_BASIC_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to remove potentially dangerous characters.

    Args:
        filename: The filename to sanitize.

    Returns:
        Sanitized filename safe for filesystem use.

    Examples:
        >>> sanitize_filename("my file<script>.txt")
        "my_filescript.txt"
        >>> sanitize_filename("../../../etc/passwd")
        "etcpasswd"
    """
    if not filename:
        return "unnamed"

    # Remove path separators
    filename = filename.replace("/", "").replace("\\", "")

    # Remove unsafe characters
    filename = FILENAME_SAFE_PATTERN.sub("", filename)

    # Replace spaces with underscores
    filename = filename.replace(" ", "_")

    # Remove leading/trailing dots and dashes
    filename = filename.strip(".-_")

    # Limit length
    if len(filename) > 255:
        name_part = filename[:200]
        ext_idx = filename.rfind(".")
        if ext_idx > 0:
            ext = filename[ext_idx:][:50]
            filename = name_part + ext
        else:
            filename = name_part

    return filename or "unnamed"


def sanitize_filename_basic(filename: str, *, default: str = "export") -> str:
    """
    Sanitize a filename using a strict ASCII-safe allowlist.

    Args:
        filename: Raw filename.
        default: Fallback name when the cleaned value is empty.

    Returns:
        Sanitized filename using only letters, numbers, dot, underscore, and dash.
    """
    if not filename:
        return default
    cleaned = FILENAME_BASIC_PATTERN.sub("_", str(filename)).strip("._")
    return cleaned or default


def sanitize_query(query: str) -> str:
    """
    Sanitize a GraphQL query string for logging.

    Removes potentially sensitive information while preserving query structure.

    Args:
        query: The GraphQL query string.

    Returns:
        Sanitized query string.

    Examples:
        >>> sanitize_query("query { user(password: \\"secret\\") { id } }")
        "query { user(password: \\"[REDACTED]\\") { id } }"
    """
    if not query:
        return ""

    # Redact password-like values
    sensitive_patterns = [
        (r'(password\s*:\s*)"[^"]*"', r'\1"[REDACTED]"'),
        (r"(password\s*:\s*)'[^']*'", r"\1'[REDACTED]'"),
        (r'(token\s*:\s*)"[^"]*"', r'\1"[REDACTED]"'),
        (r'(secret\s*:\s*)"[^"]*"', r'\1"[REDACTED]"'),
        (r'(apiKey\s*:\s*)"[^"]*"', r'\1"[REDACTED]"'),
        (r'(api_key\s*:\s*)"[^"]*"', r'\1"[REDACTED]"'),
    ]

    result = query
    for pattern, replacement in sensitive_patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


def sanitize_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize GraphQL variables for logging.

    Redacts sensitive fields while preserving structure.

    Args:
        variables: The variables dictionary.

    Returns:
        Sanitized variables dictionary.

    Examples:
        >>> sanitize_variables({"username": "john", "password": "secret123"})
        {"username": "john", "password": "[REDACTED]"}
    """
    if not variables:
        return {}

    sensitive_keys = {
        "password", "token", "secret", "apiKey", "api_key",
        "accessToken", "access_token", "refreshToken", "refresh_token",
        "authorization", "auth", "credential", "credentials",
    }

    result = {}
    for key, value in variables.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = sanitize_variables(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize_variables(v) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            result[key] = value

    return result


def sanitize_html(content: str) -> str:
    """
    Sanitize HTML content by escaping special characters.

    Args:
        content: HTML content to sanitize.

    Returns:
        Escaped HTML content.

    Examples:
        >>> sanitize_html("<script>alert('xss')</script>")
        "&lt;script&gt;alert('xss')&lt;/script&gt;"
    """
    if not content:
        return ""
    return html.escape(content)


def escape_css(value: str) -> str:
    """
    Escape a value for safe use in CSS.

    Args:
        value: Value to escape.

    Returns:
        CSS-safe value.

    Examples:
        >>> escape_css("url('javascript:alert(1)')")
        "url('javascript:alert(1)')"
    """
    if not value:
        return ""

    # Remove potentially dangerous CSS
    dangerous_patterns = [
        r"expression\s*\(",
        r"javascript\s*:",
        r"behavior\s*:",
        r"-moz-binding\s*:",
    ]

    result = value
    for pattern in dangerous_patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    return result


def sanitize_log_value(value: Any) -> Any:
    """
    Sanitize a value for safe logging.

    Args:
        value: Value to sanitize.

    Returns:
        Sanitized value safe for logging.
    """
    if value is None:
        return None

    if isinstance(value, str):
        # Truncate very long strings
        if len(value) > 1000:
            return value[:1000] + "...[truncated]"
        return value

    if isinstance(value, dict):
        return sanitize_variables(value)

    if isinstance(value, (list, tuple)):
        if len(value) > 100:
            return list(value[:100]) + ["...[truncated]"]
        return [sanitize_log_value(v) for v in value]

    return value
