"""
Template access evaluation and authorization.

This module provides functions to evaluate whether a user has access to
a PDF template based on authentication, roles, permissions, and guards.
"""

import inspect
import logging
from typing import Any, Callable, Optional

from django.db import models
from django.http import HttpRequest, JsonResponse

from .registry import TemplateDefinition, TemplateAccessDecision, _clean_client_value
from ...utils.request import resolve_request_user

logger = logging.getLogger(__name__)

# Optional GraphQL metadata and permission helpers
try:
    from rail_django.core.meta import get_model_graphql_meta
except ImportError:
    get_model_graphql_meta = None

try:
    from rail_django.extensions.auth import get_user_from_token
except ImportError:
    get_user_from_token = None

try:
    from rail_django.extensions.permissions import (
        OperationType,
        permission_manager,
    )
except ImportError:
    OperationType = None
    permission_manager = None

try:
    from rail_django.security.rbac import role_manager
except ImportError:
    role_manager = None


def _resolve_request_user(request: HttpRequest):
    """
    Retrieve a user from the request session or Authorization header.
    """
    return resolve_request_user(request, get_user_from_token=get_user_from_token)


def evaluate_template_access(
    template_def: TemplateDefinition,
    user: Optional[Any],
    *,
    instance: Optional[models.Model] = None,
) -> TemplateAccessDecision:
    """
    Determine whether a user can access a registered template.

    Args:
        template_def: Template definition entry.
        user: Django user (may be anonymous/None).
        instance: Optional model instance for guard evaluation.

    Returns:
        TemplateAccessDecision describing the authorization result.
    """

    is_authenticated = bool(user and getattr(user, "is_authenticated", False))

    if template_def.require_authentication and not is_authenticated:
        return TemplateAccessDecision(
            allowed=False,
            reason="Vous devez etre authentifie pour acceder a ce document.",
            status_code=401,
        )

    if not is_authenticated:
        # Anonymous access explicitly allowed; no further checks required.
        return TemplateAccessDecision(allowed=True)

    if getattr(user, "is_superuser", False):
        return TemplateAccessDecision(allowed=True)

    required_permissions = tuple(template_def.permissions or ())
    if required_permissions and not any(
        user.has_perm(permission) for permission in required_permissions
    ):
        return TemplateAccessDecision(
            allowed=False,
            reason="Permission manquante pour generer ce document.",
            status_code=403,
        )

    required_roles = tuple(template_def.roles or ())
    if required_roles:
        if not role_manager:
            logger.warning(
                "Role manager unavailable while enforcing template roles for %s",
                template_def.url_path,
            )
            return TemplateAccessDecision(
                allowed=False,
                reason="Le controle des roles est indisponible.",
                status_code=403,
            )
        try:
            user_roles = set(role_manager.get_user_roles(user))
        except Exception as exc:
            logger.warning("Unable to fetch roles for %s: %s", user, exc)
            user_roles = set()

        if not user_roles.intersection(set(required_roles)):
            return TemplateAccessDecision(
                allowed=False,
                reason="Role requis manquant pour ce document.",
                status_code=403,
            )

    if permission_manager and OperationType and template_def.model:
        try:
            model_label = template_def.model._meta.label_lower
            permission_state = permission_manager.check_operation_permission(
                user, model_label, OperationType.READ
            )
        except Exception as exc:
            logger.warning(
                "Permission manager check failed for %s: %s (denying access)",
                template_def.model.__name__,
                exc,
            )
            return TemplateAccessDecision(
                allowed=False,
                reason="Verification de permission indisponible.",
                status_code=403,
            )
        else:
            if not permission_state.allowed:
                return TemplateAccessDecision(
                    allowed=False,
                    reason=permission_state.reason or "Acces refuse pour ce document.",
                    status_code=403,
                )

    if template_def.model and instance is None:
        return TemplateAccessDecision(allowed=True)

    guard_name = template_def.guard or ("retrieve" if template_def.model else None)
    if guard_name and template_def.model:
        if not get_model_graphql_meta:
            logger.warning(
                "GraphQL meta unavailable while enforcing template guard '%s' for %s",
                guard_name,
                template_def.url_path,
            )
            return TemplateAccessDecision(
                allowed=False,
                reason="Le controle d'acces est indisponible.",
                status_code=403,
            )

        graphql_meta = None
        try:
            graphql_meta = get_model_graphql_meta(template_def.model)
        except Exception as exc:
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
            except Exception as exc:
                logger.warning(
                    "Failed to evaluate guard '%s' for %s: %s (denying access)",
                    guard_name,
                    template_def.model.__name__,
                    exc,
                )
                return TemplateAccessDecision(
                    allowed=False,
                    reason="Garde d'operation indisponible.",
                    status_code=403,
                )

            if (
                guard_state
                and guard_state.get("guarded")
                and not guard_state.get("allowed", True)
            ):
                return TemplateAccessDecision(
                    allowed=False,
                    reason=guard_state.get("reason")
                    or "Acces refuse par la garde d'operation.",
                    status_code=403,
                )

    return TemplateAccessDecision(allowed=True)


def authorize_template_access(
    request: HttpRequest,
    template_def: TemplateDefinition,
    instance: Optional[models.Model] = None,
) -> Optional[JsonResponse]:
    """
    Authorize access to a PDF template and return a denial response if not allowed.

    Args:
        request: The HTTP request.
        template_def: Template definition to check access for.
        instance: Optional model instance for guard evaluation.

    Returns:
        JsonResponse with error details if access denied, None if allowed.
    """
    user = _resolve_request_user(request)
    decision = evaluate_template_access(
        template_def,
        user=user,
        instance=instance,
    )
    if decision.allowed:
        return None
    detail = decision.reason or (
        "Vous devez etre authentifie pour acceder a ce document."
        if decision.status_code == 401
        else "Acces refuse pour ce document."
    )
    return JsonResponse(
        {"error": "Forbidden", "detail": detail}, status=decision.status_code
    )


def _extract_client_data(
    request: HttpRequest, template_def: TemplateDefinition
) -> dict[str, Any]:
    """
    Extract whitelisted client-provided values from the request (query params only).
    """

    if not template_def.allow_client_data:
        return {}

    allowed_keys = {str(k) for k in (template_def.client_data_fields or [])}
    # If schema provided, use its names for additional allowance
    if template_def.client_data_schema:
        for entry in template_def.client_data_schema:
            name = str(entry.get("name", "")).strip()
            if name:
                allowed_keys.add(name)
    if not allowed_keys:
        return {}

    data: dict[str, Any] = {}
    for key in allowed_keys:
        if key in request.GET:
            data[key] = _clean_client_value(request.GET.get(key))

    return data


def _call_model_method(method: Optional[Callable], request: HttpRequest) -> Any:
    if not callable(method):
        return {}
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method()

    params = signature.parameters
    request_param = params.get("request")
    if not request_param:
        for param in params.values():
            if param.annotation is HttpRequest:
                request_param = param
                break
    if request_param:
        if request_param.kind == request_param.KEYWORD_ONLY:
            return method(request=request)
        return method(request)
    has_var_keyword = any(
        param.kind == param.VAR_KEYWORD for param in params.values()
    )
    has_var_positional = any(
        param.kind == param.VAR_POSITIONAL for param in params.values()
    )
    if has_var_keyword:
        return method(request=request)
    if has_var_positional:
        return method(request)
    return method()


def _call_function_handler(
    handler: Callable, request: HttpRequest, pk: Optional[str]
) -> Any:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler(request, pk)

    params = signature.parameters
    positional_params = [
        param
        for param in params.values()
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    allows_varargs = any(param.kind == param.VAR_POSITIONAL for param in params.values())
    accepts_kwargs = any(param.kind == param.VAR_KEYWORD for param in params.values())
    request_param = params.get("request")
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    if request_param:
        if request_param.kind == request_param.KEYWORD_ONLY:
            kwargs["request"] = request
        else:
            args.append(request)
    elif accepts_kwargs:
        kwargs["request"] = request

    if pk is not None:
        if len(args) < len(positional_params) or allows_varargs:
            args.append(pk)
        elif "pk" in params:
            kwargs["pk"] = pk
        elif "id" in params:
            kwargs["id"] = pk
        elif accepts_kwargs:
            kwargs["pk"] = pk

    return handler(*args, **kwargs)


def _build_template_context(
    request: HttpRequest,
    instance: Optional[models.Model],
    template_def: TemplateDefinition,
    client_data: Optional[dict[str, Any]] = None,
    pk: Optional[str] = None,
) -> dict[str, Any]:
    data: Any = {}
    if template_def.source == "model":
        method = getattr(instance, template_def.method_name or "", None)
        data = _call_model_method(method, request)
    elif template_def.handler:
        data = _call_function_handler(template_def.handler, request, pk)

    return {
        "instance": instance,
        "data": data,
        "request": request,
        "template_config": template_def.config,
        "client_data": client_data or {},
    }
