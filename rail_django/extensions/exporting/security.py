"""Export Security and Access Control

This module provides security functions for access control, rate limiting,
and permission checking in the exporting package.
"""

from typing import Any, Iterable, Optional

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse

from ...utils.network import get_rate_limit_identifier as _get_rate_limit_identifier
from ...utils.network import is_trusted_proxy as _is_trusted_proxy
from ..async_jobs import job_access_allowed as _job_access_allowed
from .config import get_export_settings, is_model_allowed

# Import auth decorators
try:
    from ..auth_decorators import jwt_required
except ImportError:
    jwt_required = None

# Import permission management
try:
    from ..permissions import OperationType, permission_manager
except ImportError:
    OperationType = None
    permission_manager = None

# Import audit logging
try:
    from ...security import security, EventType, Outcome
except ImportError:
    security = None
    EventType = None
    Outcome = None

# Import field permissions
try:
    from ...security.field_permissions import (
        FieldAccessLevel,
        FieldContext,
        field_permission_manager,
    )
except ImportError:
    FieldAccessLevel = None
    FieldContext = None
    field_permission_manager = None

# Check JWT availability
JWT_REQUIRED_AVAILABLE = jwt_required is not None
if jwt_required is None:

    def _missing_jwt_required(view_func):
        raise ImproperlyConfigured(
            "Export endpoints require JWT auth; install auth_decorators to enable."
        )

    jwt_required_decorator = _missing_jwt_required
else:
    jwt_required_decorator = jwt_required


def job_access_allowed(request: Any, job: dict[str, Any]) -> bool:
    """Check if a user is allowed to access an export job.

    Access is granted if:
    - User is authenticated and is a superuser
    - User is authenticated and is the owner of the job

    Args:
        request: Django request object.
        job: Job metadata dictionary.

    Returns:
        True if access is allowed, False otherwise.
    """
    return _job_access_allowed(request, job)


def is_trusted_proxy(remote_addr: str, trusted_proxies: Iterable[str]) -> bool:
    """Check if the remote address is in the trusted proxy list.

    Supports both individual IP addresses and CIDR notation.

    Args:
        remote_addr: Client IP address.
        trusted_proxies: List of trusted proxy addresses/networks.

    Returns:
        True if the address is a trusted proxy, False otherwise.
    """
    return _is_trusted_proxy(remote_addr, trusted_proxies)


def get_rate_limit_identifier(request: Any, export_settings: dict[str, Any]) -> str:
    """Resolve the rate limit identifier for the request.

    For authenticated users, uses user ID. For anonymous requests,
    uses IP address (respecting trusted proxies for X-Forwarded-For).

    Args:
        request: Django request object.
        export_settings: Export configuration dictionary.

    Returns:
        Rate limit identifier string (e.g., "user:123" or "ip:192.168.1.1").
    """
    rate_limit = export_settings.get("rate_limit") or {}
    trusted_proxies = rate_limit.get("trusted_proxies") or []
    return _get_rate_limit_identifier(request, trusted_proxies)


def check_rate_limit(
    request: Any, export_settings: dict[str, Any]
) -> Optional[JsonResponse]:
    """Apply a basic rate limit using Django cache.

    Args:
        request: Django request object.
        export_settings: Export configuration dictionary.

    Returns:
        JsonResponse with 429 status if rate limit exceeded, None otherwise.
    """
    config = export_settings.get("rate_limit") or {}
    if not config.get("enable", True):
        return None

    window_seconds = int(config.get("window_seconds", 60))
    max_requests = int(config.get("max_requests", 30))
    identifier = get_rate_limit_identifier(request, export_settings)
    cache_key = f"rail:export_rl:{identifier}"

    count = cache.get(cache_key)
    if count is None:
        cache.add(cache_key, 1, timeout=window_seconds)
        return None

    if int(count) >= max_requests:
        return JsonResponse(
            {"error": "Rate limit exceeded", "retry_after": window_seconds},
            status=429,
        )

    try:
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, int(count) + 1, timeout=window_seconds)
    return None


def enforce_model_permissions(
    request: Any, model: type, export_settings: dict[str, Any]
) -> Optional[JsonResponse]:
    """Check model allowlist and permissions.

    Validates that:
    - Model is in allowed_models list (if configured)
    - User is authenticated
    - User has required permissions (if configured)

    Args:
        request: Django request object.
        model: Django model class.
        export_settings: Export configuration dictionary.

    Returns:
        JsonResponse with error if permission denied, None if allowed.
    """
    if not is_model_allowed(model, export_settings):
        return JsonResponse(
            {"error": "Model export not allowed", "model": model._meta.label},
            status=403,
        )

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return JsonResponse(
            {"error": "Authentication required for export"}, status=401
        )

    if not export_settings.get("require_model_permissions", True):
        return None

    if getattr(user, "is_superuser", False):
        return None

    required_permissions = export_settings.get("required_permissions") or []
    if required_permissions:
        if not any(user.has_perm(perm) for perm in required_permissions):
            return JsonResponse(
                {"error": "Insufficient permissions for export"}, status=403
            )
        return None

    if permission_manager and OperationType:
        result = permission_manager.check_operation_permission(
            user, model._meta.label_lower, OperationType.READ
        )
        if not result.allowed:
            return JsonResponse(
                {
                    "error": "Insufficient permissions for export",
                    "detail": result.reason,
                },
                status=403,
            )

    view_perm = f"{model._meta.app_label}.view_{model._meta.model_name}"
    if not user.has_perm(view_perm):
        return JsonResponse(
            {"error": "Insufficient permissions for export"}, status=403
        )

    return None


def log_export_event(
    request: Any,
    *,
    success: bool,
    error_message: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Log an audit event for export activity.

    Args:
        request: Django request object.
        success: Whether the export was successful.
        error_message: Error message if failed.
        details: Additional audit details.
    """
    if not security or not EventType:
        return

    audit_details = {"action": "export"}
    if details:
        audit_details.update(details)

    security.emit(
        EventType.DATA_EXPORT,
        request=request,
        outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
        action="Data export",
        context=audit_details,
        error=error_message
    )


def check_template_access(request: Any, template: dict[str, Any]) -> bool:
    """Check whether a user can access an export template.

    Args:
        request: Django request object.
        template: Template configuration dictionary.

    Returns:
        True if access is allowed, False otherwise.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    if template.get("shared", False):
        return True

    required_permissions = template.get("required_permissions") or template.get(
        "permissions"
    )
    if required_permissions:
        if isinstance(required_permissions, str):
            required_permissions = [required_permissions]
        if any(user.has_perm(perm) for perm in required_permissions):
            return True
        return False

    allowed_groups = template.get("allowed_groups") or []
    if allowed_groups:
        if isinstance(allowed_groups, str):
            allowed_groups = [allowed_groups]
        if user.groups.filter(name__in=list(allowed_groups)).exists():
            return True
        return False

    allowed_users = template.get("allowed_users") or []
    if allowed_users:
        if isinstance(allowed_users, (str, int)):
            allowed_users = [allowed_users]
        if str(user.id) in {str(value) for value in allowed_users}:
            return True
        if getattr(user, "username", None) in {str(value) for value in allowed_users}:
            return True
        return False

    return False
