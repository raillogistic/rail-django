"""
Security utilities for Rail Django GraphQL.

This module implements security-related settings from LIBRARY_DEFAULTS
including authentication, authorization, rate limiting, and input validation.
"""

import logging
from functools import wraps
from typing import Any, Dict, List, Optional, Union

from django.contrib.auth.models import AnonymousUser

from .services import get_rate_limiter as get_unified_rate_limiter
from ..security.input_validation import InputValidator as UnifiedInputValidator
from .runtime_settings import RuntimeSettings

logger = logging.getLogger(__name__)


SecuritySettings = RuntimeSettings


class AuthenticationManager:
    """Handle GraphQL authentication."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = RuntimeSettings.from_schema(schema_name)

    def authenticate_user(self, request: Any) -> Union[Any, AnonymousUser]:
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

    def _authenticate_token(self, token: str) -> Optional[Any]:
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
        self.settings = RuntimeSettings.from_schema(schema_name)

    def check_field_permission(
        self, user: Any, model_name: str, field_name: str, action: str = "read"
    ) -> bool:
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

    def check_object_permission(
        self, user: Any, obj: Any, action: str = "read"
    ) -> bool:
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
    """Compatibility wrapper around the unified rate limiting engine."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self._limiter = get_unified_rate_limiter(schema_name)

    def check_rate_limit(self, identifier: str, window: str = "minute") -> bool:
        """
        Legacy compatibility: identifier can be user or ip. Window is ignored and
        delegated to the unified configuration (multiple rules can apply).
        """
        user = None
        ip = None
        if identifier.startswith("user:"):
            user_id = identifier.split(":", 1)[1]
            user = type("_UserStub", (), {"id": user_id, "is_authenticated": True})()
        elif identifier.startswith("ip:"):
            ip = identifier.split(":", 1)[1]
        else:
            ip = identifier

        result = self._limiter.check("graphql", user=user, ip=ip)
        return result.allowed

    def get_client_identifier(self, request: Any) -> str:
        if hasattr(request, "user") and request.user.is_authenticated:
            return f"user:{request.user.id}"
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "unknown")
        return f"ip:{ip}"

    def rate_limit(self, func):
        """Decorator to apply unified rate limiting to GraphQL resolvers."""
        @wraps(func)
        def wrapper(root, info, **kwargs):
            result = self._limiter.check("graphql", request=info.context)
            if not result.allowed:
                raise PermissionError("Rate limit exceeded")
            return func(root, info, **kwargs)

        return wrapper


class InputValidator:
    """Compatibility wrapper for unified input validation."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self._validator = UnifiedInputValidator(schema_name)

    def validate_input(self, input_data: Dict[str, Any]) -> List[str]:
        report = self._validator.validate_payload(input_data)
        return report.error_messages()

    def validate_payload(self, input_data: Any) -> Any:
        return self._validator.validate_payload(input_data)

    def validate_and_sanitize(self, model_name: Optional[str], input_data: Dict[str, Any]) -> Dict[str, Any]:
        return self._validator.validate_input(model_name, input_data)


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
