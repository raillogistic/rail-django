"""
Utilities for normalizing and evaluating custom mutation access rules.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


MutationAccessConfig = dict[str, Any]


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        normalized.append(token)
        seen.add(token)
    return normalized


def normalize_mutation_access(
    *,
    permissions: Any = None,
    roles: Any = None,
    resolver: Optional[Callable[..., Any]] = None,
    match: Optional[str] = None,
    existing: Optional[MutationAccessConfig] = None,
) -> Optional[MutationAccessConfig]:
    """
    Normalize mutation access declarations into a consistent payload.
    """
    payload = dict(existing or {})

    merged_permissions = _normalize_string_list(payload.get("permissions"))
    merged_roles = _normalize_string_list(payload.get("roles"))

    for permission in _normalize_string_list(permissions):
        if permission not in merged_permissions:
            merged_permissions.append(permission)
    for role in _normalize_string_list(roles):
        if role not in merged_roles:
            merged_roles.append(role)

    if resolver is None:
        resolver = payload.get("resolver")

    match_mode = str(match or payload.get("match") or "all").strip().lower()
    if match_mode not in {"all", "any"}:
        match_mode = "all"

    resolver_name = str(payload.get("resolver_name") or "").strip()
    if callable(resolver):
        resolver_name = getattr(resolver, "__name__", None) or resolver_name

    normalized: MutationAccessConfig = {
        "permissions": merged_permissions,
        "roles": merged_roles,
        "resolver": resolver,
        "resolver_name": str(resolver_name or "").strip() or None,
        "match": match_mode,
    }
    if not normalized["permissions"] and not normalized["roles"] and not normalized["resolver"]:
        return None
    return normalized


def get_mutation_access_config(target: Any) -> Optional[MutationAccessConfig]:
    """
    Read and normalize all legacy and current mutation access attributes.
    """
    normalized = normalize_mutation_access(
        existing=getattr(target, "_mutation_access", None)
    )
    permissions = getattr(target, "_requires_permissions", None)
    if permissions is None:
        legacy_permission = getattr(target, "_requires_permission", None)
        permissions = [legacy_permission] if legacy_permission else None
    return normalize_mutation_access(
        permissions=permissions,
        existing=normalized,
    )


def apply_mutation_access(target: Any, access: Optional[MutationAccessConfig]) -> None:
    """
    Persist normalized mutation access metadata on a decorated callable.
    """
    if access is None:
        if hasattr(target, "_mutation_access"):
            delattr(target, "_mutation_access")
        if hasattr(target, "_requires_permissions"):
            delattr(target, "_requires_permissions")
        if hasattr(target, "_requires_permission"):
            delattr(target, "_requires_permission")
        return

    target._mutation_access = access
    target._requires_permissions = list(access.get("permissions") or [])
    permissions = target._requires_permissions
    target._requires_permission = permissions[0] if len(permissions) == 1 else None


def _resolve_role_manager():
    from ..security.rbac import role_manager

    return role_manager


def _user_has_required_permission(user: Any, permission: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False

    has_perm = getattr(user, "has_perm", None)
    if callable(has_perm):
        try:
            if has_perm(permission):
                return True
        except Exception:
            pass

    try:
        role_manager = _resolve_role_manager()
        effective_permissions = role_manager.get_effective_permissions(user)
        return role_manager._permission_in_effective_permissions(
            permission,
            effective_permissions,
        )
    except Exception:
        return False


def _invoke_access_resolver(
    resolver: Callable[..., Any],
    *,
    user: Any,
    info: Any,
    instance: Any,
    input_data: Any,
    model: Any,
    method: Any,
    root: Any,
) -> tuple[bool, Optional[str]]:
    kwargs = {
        "user": user,
        "info": info,
        "instance": instance,
        "input": input_data,
        "input_data": input_data,
        "model": model,
        "method": method,
        "root": root,
    }
    try:
        signature = inspect.signature(resolver)
    except (TypeError, ValueError):
        signature = None

    try:
        if signature is None:
            result = resolver(**kwargs)
        else:
            parameters = signature.parameters
            accepts_kwargs = any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if accepts_kwargs:
                result = resolver(**kwargs)
            else:
                accepted_kwargs = {
                    name: value
                    for name, value in kwargs.items()
                    if name in parameters
                }
                result = resolver(**accepted_kwargs)
    except Exception as exc:
        logger.warning("Failed to evaluate mutation access resolver: %s", exc)
        return False, "Access resolver denied this mutation"

    if isinstance(result, dict):
        allowed = bool(result.get("allowed", False))
        reason = result.get("reason")
        return allowed, str(reason) if reason else None
    if isinstance(result, (list, tuple)) and result:
        allowed = bool(result[0])
        reason = result[1] if len(result) > 1 else None
        return allowed, str(reason) if reason else None
    return bool(result), None


def evaluate_mutation_access(
    access: Optional[MutationAccessConfig],
    *,
    user: Any,
    info: Any = None,
    instance: Any = None,
    input_data: Any = None,
    model: Any = None,
    method: Any = None,
    root: Any = None,
) -> dict[str, Any]:
    """
    Evaluate normalized mutation access metadata.

    Roles and permissions are strict within each category, but any configured
    category can grant access. That lets a mutation authorize through RBAC,
    Django permissions, or a custom resolver.
    """
    normalized = normalize_mutation_access(existing=access)
    required_permissions = list((normalized or {}).get("permissions") or [])
    required_roles = list((normalized or {}).get("roles") or [])
    resolver = (normalized or {}).get("resolver")
    resolver_name = (normalized or {}).get("resolver_name")
    match_mode = str((normalized or {}).get("match") or "all").strip().lower()
    has_rules = bool(required_permissions or required_roles or resolver)

    result = {
        "allowed": True,
        "required_permissions": required_permissions,
        "required_roles": required_roles,
        "resolver_name": resolver_name,
        "match": match_mode,
        "requires_authentication": has_rules,
        "reason": None,
    }
    if not has_rules:
        return result

    if user and getattr(user, "is_superuser", False):
        return result

    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    if not is_authenticated:
        result["allowed"] = False
        result["reason"] = "Authentication required"
        return result

    checks: list[tuple[bool, str]] = []

    if required_roles:
        role_manager = _resolve_role_manager()
        try:
            user_roles = {
                str(role).strip()
                for role in role_manager.get_user_roles(user)
                if str(role).strip()
            }
        except Exception:
            user_roles = set()
        missing_roles = [role for role in required_roles if role not in user_roles]
        checks.append((not missing_roles, f"Role required: {', '.join(required_roles)}"))

    if required_permissions:
        missing_permissions = [
            permission
            for permission in required_permissions
            if not _user_has_required_permission(user, permission)
        ]
        checks.append(
            (
                not missing_permissions,
                f"Permission required: {', '.join(required_permissions)}",
            )
        )

    if callable(resolver):
        resolver_allowed, resolver_reason = _invoke_access_resolver(
            resolver,
            user=user,
            info=info,
            instance=instance,
            input_data=input_data,
            model=model,
            method=method,
            root=root,
        )
        checks.append(
            (
                resolver_allowed,
                resolver_reason or "Access resolver denied this mutation",
            )
        )

    if match_mode == "any":
        if any(check_allowed for check_allowed, _ in checks):
            return result
    else:
        if all(check_allowed for check_allowed, _ in checks):
            return result

    result["allowed"] = False
    joiner = " or " if match_mode == "any" else " and "
    result["reason"] = joiner.join(
        reason for _, reason in checks if str(reason or "").strip()
    ) or "Permission denied"
    return result
