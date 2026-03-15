"""User-scoped table view-state helpers for bootstrap payloads."""

from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

DEFAULT_TABLE_PAGE_SIZE = 10
VALID_TABLE_DENSITIES = {"compact", "comfortable", "spacious"}


def normalize_table_persistence_keys(key: str | None) -> list[str]:
    trimmed = str(key or "").strip()
    if not trimmed:
        return []

    variants = [trimmed]
    if trimmed.endswith("/"):
        without_trailing_slash = trimmed.rstrip("/")
        if without_trailing_slash:
            variants.append(without_trailing_slash)
    else:
        variants.append(f"{trimmed}/")

    return variants


def _decode_json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    decoded = value
    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return {}
        try:
            decoded = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}

    return decoded if isinstance(decoded, dict) else {}


def _coerce_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return None
        try:
            parsed = float(raw_value)
        except ValueError:
            return None
        if parsed > 0:
            return int(parsed)
    return None


def _coerce_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return None
        try:
            parsed = float(raw_value)
        except ValueError:
            return None
        if parsed >= 0:
            return int(parsed)
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        return [trimmed] if trimmed else []
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


def _coerce_boolean_mapping(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): boolean_value
        for key, boolean_value in value.items()
        if isinstance(key, str) and isinstance(boolean_value, bool)
    }


def _coerce_positive_int_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, int] = {}
    for key, raw_width in value.items():
        if not isinstance(key, str):
            continue
        width = _coerce_positive_int(raw_width)
        if width is not None:
            normalized[key] = width
    return normalized


def _resolve_user_settings(user: Any) -> Any | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None

    try:
        settings_obj = getattr(user, "settings", None)
    except ObjectDoesNotExist:
        return None

    return settings_obj


def get_user_table_configs(user: Any) -> dict[str, Any]:
    settings_obj = _resolve_user_settings(user)
    if settings_obj is None:
        return {}

    raw_configs = getattr(settings_obj, "table_configs", None)
    if raw_configs is None:
        raw_configs = getattr(settings_obj, "tableConfigs", None)
    return _decode_json_object(raw_configs)


def parse_persisted_table_state(
    value: Any,
    *,
    resolved_key: str | None = None,
) -> dict[str, Any] | None:
    parsed = _decode_json_object(value)
    if not parsed:
        return None

    state: dict[str, Any] = {}

    column_order = _coerce_string_list(
        parsed.get("columnOrder")
        or parsed.get("column_order")
        or parsed.get("columnorder")
    )
    if column_order:
        state["columnOrder"] = column_order

    column_visibility = _coerce_boolean_mapping(
        parsed.get("columnVisibility")
        or parsed.get("column_visibility")
        or parsed.get("columnvisibility")
    )
    if column_visibility:
        state["columnVisibility"] = column_visibility

    column_widths = _coerce_positive_int_mapping(
        parsed.get("columnWidths")
        or parsed.get("column_widths")
        or parsed.get("columnwidths")
    )
    if column_widths:
        state["columnWidths"] = column_widths

    per_page = _coerce_positive_int(
        parsed.get("perPage") or parsed.get("per_page") or parsed.get("page_size")
    )
    if per_page is not None:
        state["perPage"] = per_page

    density = parsed.get("density")
    if isinstance(density, str) and density in VALID_TABLE_DENSITIES:
        state["density"] = density

    wrap_cells = parsed.get("wrapCells")
    if wrap_cells is None:
        wrap_cells = parsed.get("wrap_cells")
    if isinstance(wrap_cells, bool):
        state["wrapCells"] = wrap_cells

    visibility_version = _coerce_non_negative_int(
        parsed.get("visibilityVersion") or parsed.get("visibility_version")
    )
    if visibility_version is not None:
        state["visibilityVersion"] = visibility_version

    ordering = _coerce_string_list(
        parsed.get("ordering") or parsed.get("orderBy") or parsed.get("order_by")
    )
    if ordering:
        state["ordering"] = ordering

    if not state:
        return None

    if resolved_key:
        state["persistenceKey"] = resolved_key

    return state


def resolve_user_table_state(
    user: Any,
    *,
    persistence_key: str | None = None,
) -> dict[str, Any] | None:
    configs = get_user_table_configs(user)
    if not configs:
        return None

    for candidate_key in normalize_table_persistence_keys(persistence_key):
        resolved = parse_persisted_table_state(
            configs.get(candidate_key),
            resolved_key=candidate_key,
        )
        if resolved:
            return resolved

    return None
