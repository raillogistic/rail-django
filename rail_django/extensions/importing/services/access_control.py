"""Permission helpers for import operations."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied


def _to_user_id(user: Any) -> str:
    if user is None:
        return ""
    raw_id = getattr(user, "id", None)
    if raw_id is None:
        return ""
    return str(raw_id)


def _has_permission(user: Any, app_label: str, model_name: str) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    model = model_name.lower()
    return bool(
        user.has_perm(f"{app_label}.view_{model}")
        or user.has_perm(f"{app_label}.change_{model}")
        or user.has_perm(f"{app_label}.add_{model}")
    )


def require_import_access(user: Any, app_label: str, model_name: str) -> str:
    """Validate import access and return normalized user id."""
    if not _has_permission(user, app_label=app_label, model_name=model_name):
        raise PermissionDenied(
            f"User is not allowed to import data for {app_label}.{model_name}."
        )
    return _to_user_id(user)

