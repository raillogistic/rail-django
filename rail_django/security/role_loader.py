"""
Role definition loader for roles.json files.

This module scans installed Django apps for roles.json files and registers
their roles with the RBAC role manager.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

from django.apps import apps

from .rbac import RoleDefinition, RoleType, role_manager

logger = logging.getLogger(__name__)


def load_app_role_definitions(
    app_configs: Optional[Iterable[object]] = None,
) -> int:
    """
    Load roles.json files from installed apps and register role definitions.

    Args:
        app_configs: Optional iterable of Django app configs. Defaults to all
            installed apps.

    Returns:
        Number of role definitions registered from role files.
    """
    if app_configs is None:
        app_configs = apps.get_app_configs()

    registered_count = 0
    for app_config in app_configs:
        app_path = getattr(app_config, "path", None)
        if not app_path:
            continue
        roles_path = Path(app_path) / "roles.json"
        if not roles_path.exists():
            continue
        try:
            content = roles_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("Could not read roles file %s: %s", roles_path, exc)
            continue
        if not content:
            logger.debug("Skipping empty roles file %s", roles_path)
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in roles file %s: %s", roles_path, exc)
            continue

        roles = _extract_roles(payload, roles_path)
        for role_data in roles:
            role_definition = _build_role_definition(role_data, roles_path)
            if role_definition is None:
                continue
            role_manager.register_role(role_definition)
            registered_count += 1

    return registered_count


def _extract_roles(payload: object, roles_path: Path) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        roles = payload.get("roles", [])
    else:
        roles = payload
    if roles is None:
        return []
    if not isinstance(roles, list):
        logger.warning("Roles file %s must define a list of roles", roles_path)
        return []
    normalized: list[dict[str, object]] = []
    for entry in roles:
        if not isinstance(entry, dict):
            logger.warning("Role entry in %s must be an object", roles_path)
            continue
        normalized.append(entry)
    return normalized


def _build_role_definition(
    role_data: dict[str, object],
    roles_path: Path,
) -> Optional[RoleDefinition]:
    name = role_data.get("name")
    if not name or not isinstance(name, str):
        logger.warning("Role entry missing name in %s", roles_path)
        return None

    role_type = _coerce_role_type(role_data.get("role_type"))
    permissions = _coerce_list(role_data.get("permissions"))
    parent_roles = _coerce_optional_list(role_data.get("parent_roles"))

    max_users = role_data.get("max_users")
    if max_users is not None:
        try:
            max_users = int(max_users)
        except (TypeError, ValueError):
            logger.warning("Invalid max_users for role %s in %s", name, roles_path)
            max_users = None

    return RoleDefinition(
        name=name,
        description=str(role_data.get("description", "")),
        role_type=role_type,
        permissions=permissions,
        parent_roles=parent_roles,
        is_system_role=bool(role_data.get("is_system_role", False)),
        max_users=max_users,
    )


def _coerce_role_type(value: object) -> RoleType:
    if isinstance(value, RoleType):
        return value
    key = str(value or "business").lower()
    mapping = {
        "system": RoleType.SYSTEM,
        "business": RoleType.BUSINESS,
        "functional": RoleType.FUNCTIONAL,
    }
    return mapping.get(key, RoleType.BUSINESS)


def _coerce_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _coerce_optional_list(value: object) -> Optional[list[str]]:
    items = _coerce_list(value)
    return items or None
