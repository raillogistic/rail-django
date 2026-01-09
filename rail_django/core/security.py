"""
Security utilities for Rail Django GraphQL.

This module implements security-related settings from LIBRARY_DEFAULTS
including authentication, authorization, rate limiting, and input validation.
"""

import logging
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Dict, List, Optional, Set, Union

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from ..conf import get_setting

logger = logging.getLogger(__name__)
User = get_user_model()


@dataclass
class SecuritySettings:
    """Settings for security configuration."""

    enable_authentication: bool = True
    enable_authorization: bool = True
    enable_rate_limiting: bool = False
    rate_limit_requests_per_minute: int = 60
    rate_limit_requests_per_hour: int = 1000
    enable_query_depth_limiting: bool = True
    max_query_depth: int = 10
    enable_introspection: bool = True
    enable_graphiql: bool = True
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    enable_csrf_protection: bool = True
    enable_cors: bool = True
    enable_field_permissions: bool = True
    enable_object_permissions: bool = True
    enable_input_validation: bool = True
    enable_sql_injection_protection: bool = True
    enable_xss_protection: bool = True
    session_timeout_minutes: int = 30
    max_file_upload_size: int = 10485760  # 10MB
    allowed_file_types: List[str] = field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".pdf", ".txt"])

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "SecuritySettings":
        """Create SecuritySettings from schema configuration."""
        from ..defaults import LIBRARY_DEFAULTS

        defaults = LIBRARY_DEFAULTS.get("security_settings", {})

        # Override with Django settings if available
        django_security_settings = getattr(
            django_settings, 'RAIL_DJANGO_GRAPHQL', {}).get('security_settings', {})

        # Merge settings
        merged_settings = {**defaults, **django_security_settings}

        # Filter to only include valid fields
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {k: v for k, v in merged_settings.items() if k in valid_fields}

        return cls(**filtered_settings)


class AuthenticationManager:
    """Handle GraphQL authentication."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = SecuritySettings.from_schema(schema_name)

    def authenticate_user(self, request: Any) -> Union[User, AnonymousUser]:
        """
        Authenticate user from request.

        Args:
            request: Django request object

        Returns:
            Authenticated user or AnonymousUser
        """
        if not self.settings.enable_authentication:
            return AnonymousUser()

        # Check session authentication
        if hasattr(request, 'user') and request.user.is_authenticated:
            return request.user

        # Check token authentication
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            user = self._authenticate_token(token)
            if user:
                return user

        return AnonymousUser()

    def _authenticate_token(self, token: str) -> Optional[User]:
        """Authenticate user by token."""
        try:
            # This would integrate with your token authentication system
            # For now, return None (not implemented)
            return None
        except Exception as e:
            logger.warning(f"Token authentication failed: {e}")
            return None

    def require_authentication(self, func):
        """Decorator to require authentication for GraphQL resolvers."""
        @wraps(func)
        def wrapper(root, info, **kwargs):
            user = self.authenticate_user(info.context)
            if isinstance(user, AnonymousUser):
                raise PermissionError("Authentication required")

            # Add user to context
            info.context.user = user
            return func(root, info, **kwargs)

        return wrapper


class AuthorizationManager:
    """Handle GraphQL authorization."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = SecuritySettings.from_schema(schema_name)

    def check_field_permission(self, user: User, model_name: str, field_name: str, action: str = "read") -> bool:
        """
        Check if user has permission to access a specific field.

        Args:
            user: User instance
            model_name: Name of the model
            field_name: Name of the field
            action: Action type (read, write, delete)

        Returns:
            True if user has permission, False otherwise
        """
        if not self.settings.enable_field_permissions:
            return True

        if isinstance(user, AnonymousUser):
            return False

        # Check Django permissions
        permission_name = f"{model_name.lower()}.{action}_{field_name}"
        return user.has_perm(permission_name)

    def check_object_permission(self, user: User, obj: Any, action: str = "read") -> bool:
        """
        Check if user has permission to access a specific object.

        Args:
            user: User instance
            obj: Model instance
            action: Action type (read, write, delete)

        Returns:
            True if user has permission, False otherwise
        """
        if not self.settings.enable_object_permissions:
            return True

        if isinstance(user, AnonymousUser):
            return False

        # Check Django object-level permissions
        model_name = obj._meta.model_name
        permission_name = f"{obj._meta.app_label}.{action}_{model_name}"

        # Basic permission check
        if not user.has_perm(permission_name):
            return False

        # Object-level permission check (if using django-guardian or similar)
        if hasattr(user, 'has_perm') and hasattr(obj, '_meta'):
            return user.has_perm(permission_name, obj)

        return True

    def require_permission(self, permission: str):
        """Decorator to require specific permission for GraphQL resolvers."""
        def decorator(func):
            @wraps(func)
            def wrapper(root, info, **kwargs):
                user = getattr(info.context, 'user', AnonymousUser())
                if isinstance(user, AnonymousUser) or not user.has_perm(permission):
                    raise PermissionError(f"Permission required: {permission}")

                return func(root, info, **kwargs)

            return wrapper
        return decorator


class RateLimiter:
    """Handle rate limiting for GraphQL requests."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = SecuritySettings.from_schema(schema_name)

    def check_rate_limit(self, identifier: str, window: str = "minute") -> bool:
        """
        Check if request is within rate limits.

        Args:
            identifier: Unique identifier (IP, user ID, etc.)
            window: Time window (minute, hour)

        Returns:
            True if within limits, False if rate limited
        """
        # Rate limiting disabled: always allow
        return True

    def get_client_identifier(self, request: Any) -> str:
        """Get unique identifier for rate limiting."""
        # Try to get user ID first
        if hasattr(request, 'user') and request.user.is_authenticated:
            return f"user:{request.user.id}"

        # Fall back to IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')

        return f"ip:{ip}"

    def rate_limit(self, func):
        """Decorator to apply rate limiting to GraphQL resolvers."""
        @wraps(func)
        def wrapper(root, info, **kwargs):
            identifier = self.get_client_identifier(info.context)

            # Check both minute and hour limits
            if not self.check_rate_limit(identifier, "minute"):
                raise PermissionError("Rate limit exceeded (per minute)")

            if not self.check_rate_limit(identifier, "hour"):
                raise PermissionError("Rate limit exceeded (per hour)")

            return func(root, info, **kwargs)

        return wrapper


class InputValidator:
    """Validate GraphQL inputs for security."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = SecuritySettings.from_schema(schema_name)

    def validate_input(self, input_data: Dict[str, Any]) -> List[str]:
        """
        Validate input data for security issues.

        Args:
            input_data: Input data to validate

        Returns:
            List of validation errors
        """
        errors = []

        if not self.settings.enable_input_validation:
            return errors

        # Check for SQL injection patterns
        if self.settings.enable_sql_injection_protection:
            sql_errors = self._check_sql_injection(input_data)
            errors.extend(sql_errors)

        # Check for XSS patterns
        if self.settings.enable_xss_protection:
            xss_errors = self._check_xss(input_data)
            errors.extend(xss_errors)

        return errors

    def _check_sql_injection(self, data: Any, path: str = "") -> List[str]:
        """Check for SQL injection patterns."""
        errors = []
        sql_patterns = [
            "union select", "drop table", "delete from", "insert into",
            "update set", "exec ", "execute ", "sp_", "xp_"
        ]

        if isinstance(data, str):
            lower_data = data.lower()
            for pattern in sql_patterns:
                if pattern in lower_data:
                    errors.append(
                        f"Potential SQL injection detected in {path or 'input'}: {pattern}")

        elif isinstance(data, dict):
            for key, value in data.items():
                errors.extend(self._check_sql_injection(value, f"{path}.{key}" if path else key))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                errors.extend(self._check_sql_injection(item, f"{path}[{i}]" if path else f"[{i}]"))

        return errors

    def _check_xss(self, data: Any, path: str = "") -> List[str]:
        """Check for XSS patterns."""
        errors = []
        xss_patterns = [
            "<script", "javascript:", "onload=", "onerror=", "onclick=",
            "onmouseover=", "onfocus=", "onblur=", "onchange=", "onsubmit="
        ]

        if isinstance(data, str):
            lower_data = data.lower()
            for pattern in xss_patterns:
                if pattern in lower_data:
                    errors.append(f"Potential XSS detected in {path or 'input'}: {pattern}")

        elif isinstance(data, dict):
            for key, value in data.items():
                errors.extend(self._check_xss(value, f"{path}.{key}" if path else key))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                errors.extend(self._check_xss(item, f"{path}[{i}]" if path else f"[{i}]"))

        return errors


# Global instances
auth_manager = AuthenticationManager()
authz_manager = AuthorizationManager()
rate_limiter = RateLimiter()
input_validator = InputValidator()


def get_auth_manager(schema_name: Optional[str] = None) -> AuthenticationManager:
    """Get authentication manager instance for schema."""
    return AuthenticationManager(schema_name)


def get_authz_manager(schema_name: Optional[str] = None) -> AuthorizationManager:
    """Get authorization manager instance for schema."""
    return AuthorizationManager(schema_name)


def get_rate_limiter(schema_name: Optional[str] = None) -> RateLimiter:
    """Get rate limiter instance for schema."""
    return RateLimiter(schema_name)


def get_input_validator(schema_name: Optional[str] = None) -> InputValidator:
    """Get input validator instance for schema."""
    return InputValidator(schema_name)
