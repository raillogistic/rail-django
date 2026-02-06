"""
Load GraphQLMeta configuration from app-level meta.yaml or meta.json files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

from django.apps import apps
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency
    yaml = None

_META_CONFIGS: dict[str, object] = {}
_META_CONFIGS_LOADED = False


class JsonGraphQLMeta:
    """Simple attribute container for file-based GraphQLMeta."""

    def __init__(self, payload: dict[str, object]) -> None:
        for key, value in payload.items():
            try:
                setattr(self, key, value)
            except Exception:
                continue


def load_app_meta_configs(
    app_configs: Optional[Iterable[object]] = None,
) -> int:
    """
    Load meta.yaml or meta.json files from installed apps.

    Args:
        app_configs: Optional iterable of Django app configs. Defaults to all
            installed apps.

    Returns:
        Number of model meta definitions registered.
    """
    global _META_CONFIGS_LOADED

    if app_configs is None:
        app_configs = apps.get_app_configs()

    registered_count = 0
    for app_config in app_configs:
        app_path = getattr(app_config, "path", None)
        if not app_path:
            continue
        meta_path = _find_meta_path(app_path)
        if not meta_path:
            continue
        payload = _load_meta_payload(meta_path)
        if payload is None:
            continue

        _register_roles(payload, meta_path)
        model_configs = _extract_model_configs(payload, meta_path)
        for model_key, config in model_configs.items():
            model_label = _normalize_model_label(model_key, app_config, meta_path)
            if not model_label:
                continue
            if not isinstance(config, dict):
                logger.warning(
                    "Meta config for %s in %s must be an object",
                    model_key,
                    meta_path,
                )
                continue
            normalized = _normalize_meta_config(config, meta_path)
            _META_CONFIGS[model_label] = JsonGraphQLMeta(normalized)
            registered_count += 1

    _META_CONFIGS_LOADED = True
    return registered_count


def get_model_meta_config(model_class: object) -> Optional[object]:
    """Return the JSON meta config for a model class if present."""
    _ensure_loaded()
    if not model_class or not hasattr(model_class, "_meta"):
        return None
    label = getattr(model_class._meta, "label_lower", None)
    if not label:
        return None
    return _META_CONFIGS.get(str(label).lower())


def clear_meta_configs() -> None:
    """Clear cached JSON meta configs (primarily for tests)."""
    global _META_CONFIGS_LOADED
    _META_CONFIGS.clear()
    _META_CONFIGS_LOADED = False


def _ensure_loaded() -> None:
    if _META_CONFIGS_LOADED:
        return
    if not apps.ready:
        return
    load_app_meta_configs()


def _extract_model_configs(
    payload: object,
    meta_path: Path,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        logger.warning("Meta file %s must be a mapping", meta_path)
        return {}
    if "models" in payload:
        models = payload.get("models", {})
    elif "roles" in payload:
        models = payload.get("models", {})
    else:
        models = payload
    if models is None:
        return {}
    if not isinstance(models, dict):
        logger.warning("Meta file %s must define a models mapping", meta_path)
        return {}
    return models


def _register_roles(payload: object, meta_path: Path) -> None:
    roles = _extract_roles(payload, meta_path)
    if not roles:
        return
    try:
        from ...security.rbac import RoleDefinition, RoleType, role_manager
    except Exception as exc:
        logger.warning("Could not import RBAC components for %s: %s", meta_path, exc)
        return

    for role_data in roles:
        role_definition = _build_role_definition(
            role_data,
            meta_path,
            RoleDefinition,
            RoleType,
        )
        if role_definition is None:
            continue
        role_manager.register_role(role_definition)


def _extract_roles(payload: object, meta_path: Path) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    roles = payload.get("roles")
    if roles is None:
        return []
    if isinstance(roles, dict):
        normalized = []
        for name, entry in roles.items():
            if not isinstance(entry, dict):
                logger.warning("Role entry for %s in %s must be an object", name, meta_path)
                continue
            normalized.append({**entry, "name": name})
        return normalized
    if isinstance(roles, list):
        normalized = []
        for entry in roles:
            if not isinstance(entry, dict):
                logger.warning("Role entry in %s must be an object", meta_path)
                continue
            normalized.append(entry)
        return normalized
    logger.warning("Roles in %s must be a list or object", meta_path)
    return []


def _build_role_definition(
    role_data: dict[str, object],
    meta_path: Path,
    role_definition_cls: object,
    role_type_cls: object,
) -> Optional[object]:
    name = role_data.get("name")
    if not name or not isinstance(name, str):
        logger.warning("Role entry missing name in %s", meta_path)
        return None

    role_type = _coerce_role_type(role_data.get("role_type"), role_type_cls)
    permissions = _coerce_list(role_data.get("permissions"))
    parent_roles = _coerce_optional_list(role_data.get("parent_roles"))

    max_users = role_data.get("max_users")
    if max_users is not None:
        try:
            max_users = int(max_users)
        except (TypeError, ValueError):
            logger.warning("Invalid max_users for role %s in %s", name, meta_path)
            max_users = None

    return role_definition_cls(
        name=name,
        description=str(role_data.get("description", "")),
        role_type=role_type,
        permissions=permissions,
        parent_roles=parent_roles,
        is_system_role=bool(role_data.get("is_system_role", False)),
        max_users=max_users,
    )


def _coerce_role_type(value: object, role_type_cls: object) -> object:
    if value is None:
        normalized = "business"
    else:
        normalized = str(value).lower()
    for candidate in role_type_cls:
        if candidate.value == normalized or candidate.name.lower() == normalized:
            return candidate
    return getattr(role_type_cls, "BUSINESS", list(role_type_cls)[0])


def _coerce_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _coerce_optional_list(value: object) -> Optional[list[str]]:
    items = _coerce_list(value)
    return items or None


def _normalize_model_label(
    model_key: object,
    app_config: object,
    meta_path: Path,
) -> Optional[str]:
    if not model_key:
        return None
    key = str(model_key).strip()
    if not key:
        return None
    if "." in key:
        return key.lower()
    app_label = getattr(app_config, "label", None) or getattr(app_config, "name", "")
    if not app_label:
        logger.warning("Missing app label for meta file %s", meta_path)
        return None
    return f"{app_label}.{key}".lower()


def _normalize_meta_config(
    config: dict[str, object],
    meta_path: Path,
) -> dict[str, object]:
    normalized = dict(config)

    filtering = normalized.get("filtering")
    if isinstance(filtering, dict):
        _resolve_callable_map(filtering.get("custom"), meta_path)

    resolvers = normalized.get("resolvers")
    if isinstance(resolvers, dict):
        _resolve_callable_map(resolvers.get("queries"), meta_path)
        _resolve_callable_map(resolvers.get("mutations"), meta_path)
        _resolve_callable_map(resolvers.get("fields"), meta_path)

    access = normalized.get("access")
    if isinstance(access, dict):
        operations = access.get("operations")
        if isinstance(operations, dict):
            for guard in operations.values():
                _resolve_condition(guard, meta_path)
        fields = access.get("fields")
        if isinstance(fields, list):
            for guard in fields:
                _resolve_condition(guard, meta_path)

    _resolve_callable_map(normalized.get("custom_filters"), meta_path)
    _resolve_callable_map(normalized.get("custom_resolvers"), meta_path)

    return normalized


def _resolve_callable_map(candidate: object, meta_path: Path) -> None:
    if not isinstance(candidate, dict):
        return
    for key, value in list(candidate.items()):
        candidate[key] = _resolve_callable(value, meta_path)


def _resolve_condition(candidate: object, meta_path: Path) -> None:
    if not isinstance(candidate, dict):
        return
    if "condition" not in candidate:
        return
    candidate["condition"] = _resolve_callable(candidate.get("condition"), meta_path)


def _resolve_callable(value: object, meta_path: Path) -> object:
    if not isinstance(value, str) or "." not in value:
        return value
    try:
        resolved = import_string(value)
    except Exception as exc:
        logger.warning("Could not import callable %s from %s: %s", value, meta_path, exc)
        return value
    if callable(resolved):
        return resolved
    return value


def _find_meta_path(app_path: str) -> Optional[Path]:
    base_path = Path(app_path)
    yaml_path = base_path / "meta.yaml"
    json_path = base_path / "meta.json"
    if yaml_path.exists():
        if json_path.exists():
            logger.warning(
                "Both meta.yaml and meta.json found in %s; using meta.yaml",
                base_path,
            )
        return yaml_path
    if json_path.exists():
        return json_path
    return None


def _load_meta_payload(meta_path: Path) -> Optional[object]:
    try:
        content = meta_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("Could not read meta file %s: %s", meta_path, exc)
        return None
    if not content:
        logger.debug("Skipping empty meta file %s", meta_path)
        return None
    if meta_path.suffix == ".json":
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in meta file %s: %s", meta_path, exc)
            return None
        return payload
    if meta_path.suffix == ".yaml":
        if yaml is None:
            logger.warning("PyYAML is required to parse %s", meta_path)
            return None
        try:
            payload = yaml.safe_load(content)
        except Exception as exc:
            logger.warning("Invalid YAML in meta file %s: %s", meta_path, exc)
            return None
        if payload is None:
            logger.debug("Skipping empty meta file %s", meta_path)
            return None
        return payload
    logger.warning("Unsupported meta file type for %s", meta_path)
    return None
