"""
Excel export access control.

This module provides access control functionality for Excel templates,
including user resolution, permission checking, and guard evaluation.
"""

import logging
from typing import Any, Optional

from django.db import models
from django.http import HttpRequest, JsonResponse

from .config import ExcelTemplateAccessDecision, ExcelTemplateDefinition

# Optional imports
try:
    from rail_django.core.meta import get_model_graphql_meta
except ImportError:  # pragma: no cover
    get_model_graphql_meta = None

try:
    from rail_django.extensions.auth import get_user_from_token
except ImportError:  # pragma: no cover
    get_user_from_token = None

try:
    from rail_django.extensions.permissions import OperationType, permission_manager
except ImportError:  # pragma: no cover
    OperationType = None
    permission_manager = None

try:
    from rail_django.security.rbac import role_manager
except ImportError:  # pragma: no cover
    role_manager = None

logger = logging.getLogger(__name__)


def _resolve_request_user(request: HttpRequest):
    """
    Retrieve a user from the request session or Authorization header.

    Args:
        request: The HTTP request.

    Returns:
        The authenticated user or None.
    """
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user

    if not get_user_from_token:
        return user

    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header and (
        auth_header.startswith("Bearer ") or auth_header.startswith("Token ")
    ):
        parts = auth_header.split(" ", 1)
        if len(parts) == 2:
            token = parts[1].strip()
            if token:
                try:
                    fallback_user = get_user_from_token(token)
                except Exception:  # pragma: no cover
                    fallback_user = None
                if fallback_user and getattr(fallback_user, "is_authenticated", False):
                    request.user = fallback_user
                    return fallback_user

    return user


def evaluate_excel_template_access(
    template_def: ExcelTemplateDefinition,
    user: Optional[Any],
    *,
    instance: Optional[models.Model] = None,
) -> ExcelTemplateAccessDecision:
    """
    Determine whether a user can access a registered Excel template.

    Args:
        template_def: Template definition entry.
        user: Django user (may be anonymous/None).
        instance: Optional model instance for guard evaluation.

    Returns:
        ExcelTemplateAccessDecision describing the authorization result.
    """
    is_authenticated = bool(user and getattr(user, "is_authenticated", False))

    if template_def.require_authentication and not is_authenticated:
        return ExcelTemplateAccessDecision(
            allowed=False,
            reason="Authentication is required to access this Excel export.",
            status_code=401,
        )

    if not is_authenticated:
        return ExcelTemplateAccessDecision(allowed=True)

    if getattr(user, "is_superuser", False):
        return ExcelTemplateAccessDecision(allowed=True)

    required_permissions = tuple(template_def.permissions or ())
    if required_permissions and not any(
        user.has_perm(permission) for permission in required_permissions
    ):
        return ExcelTemplateAccessDecision(
            allowed=False,
            reason="Missing permission to generate this Excel export.",
            status_code=403,
        )

    required_roles = tuple(template_def.roles or ())
    if required_roles:
        if not role_manager:
            logger.warning(
                "Role manager unavailable while enforcing Excel template roles for %s",
                template_def.url_path,
            )
            return ExcelTemplateAccessDecision(
                allowed=False,
                reason="Role control is unavailable.",
                status_code=403,
            )
        try:
            user_roles = set(role_manager.get_user_roles(user))
        except Exception as exc:  # pragma: no cover
            logger.warning("Unable to fetch roles for %s: %s", user, exc)
            user_roles = set()

        if not user_roles.intersection(set(required_roles)):
            return ExcelTemplateAccessDecision(
                allowed=False,
                reason="Required role missing for this Excel export.",
                status_code=403,
            )

    if permission_manager and OperationType and template_def.model:
        try:
            model_label = template_def.model._meta.label_lower
            permission_state = permission_manager.check_operation_permission(
                user, model_label, OperationType.READ
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Permission manager check failed for %s: %s (denying access)",
                template_def.model.__name__,
                exc,
            )
            return ExcelTemplateAccessDecision(
                allowed=False,
                reason="Permission verification unavailable.",
                status_code=403,
            )
        else:
            if not permission_state.allowed:
                return ExcelTemplateAccessDecision(
                    allowed=False,
                    reason=permission_state.reason or "Access denied for this Excel export.",
                    status_code=403,
                )

    if template_def.model and instance is None:
        return ExcelTemplateAccessDecision(allowed=True)

    guard_name = template_def.guard or ("retrieve" if template_def.model else None)
    if guard_name and template_def.model:
        if not get_model_graphql_meta:
            logger.warning(
                "GraphQL meta unavailable while enforcing guard '%s' for %s",
                guard_name,
                template_def.url_path,
            )
            return ExcelTemplateAccessDecision(
                allowed=False,
                reason="Access control is unavailable.",
                status_code=403,
            )

        graphql_meta = None
        try:
            graphql_meta = get_model_graphql_meta(template_def.model)
        except Exception as exc:  # pragma: no cover
            logger.debug(
                "GraphQLMeta unavailable for %s: %s",
                template_def.model.__name__,
                exc,
            )

        if graphql_meta:
            guard_state = None
            try:
                guard_state = graphql_meta.describe_operation_guard(
                    guard_name,
                    user=user,
                    instance=instance,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "Failed to evaluate guard '%s' for %s: %s (denying access)",
                    guard_name,
                    template_def.model.__name__,
                    exc,
                )
                return ExcelTemplateAccessDecision(
                    allowed=False,
                    reason="Operation guard unavailable.",
                    status_code=403,
                )

            if (
                guard_state
                and guard_state.get("guarded")
                and not guard_state.get("allowed", True)
            ):
                return ExcelTemplateAccessDecision(
                    allowed=False,
                    reason=guard_state.get("reason") or "Access denied by operation guard.",
                    status_code=403,
                )

    return ExcelTemplateAccessDecision(allowed=True)


def authorize_excel_template_access(
    request: HttpRequest,
    template_def: ExcelTemplateDefinition,
    instance: Optional[models.Model] = None,
) -> Optional[JsonResponse]:
    """
    Authorize access to an Excel template and return denial response if not allowed.

    Args:
        request: The HTTP request.
        template_def: Template definition to check access for.
        instance: Optional model instance for guard evaluation.

    Returns:
        JsonResponse with error details if access denied, None if allowed.
    """
    user = _resolve_request_user(request)
    decision = evaluate_excel_template_access(
        template_def,
        user=user,
        instance=instance,
    )
    if decision.allowed:
        return None
    detail = decision.reason or (
        "Authentication is required to access this Excel export."
        if decision.status_code == 401
        else "Access denied for this Excel export."
    )
    return JsonResponse(
        {"error": "Forbidden", "detail": detail}, status=decision.status_code
    )


__all__ = [
    "_resolve_request_user",
    "evaluate_excel_template_access",
    "authorize_excel_template_access",
]
