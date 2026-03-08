"""
Relation input normalization for Form API.
"""

from __future__ import annotations

from typing import Any, Dict

from graphql import GraphQLError

PRIMARY_KEY_FIELDS = ("id", "pk", "object_id", "objectId")
SUPPORTED_RELATION_ACTIONS = frozenset(
    ("connect", "create", "update", "disconnect", "delete", "set", "clear")
)


def _extract_primary_key(value: dict[str, Any]) -> Any:
    for field_name in PRIMARY_KEY_FIELDS:
        if field_name in value and value.get(field_name) not in (None, ""):
            return value[field_name]
    return None


def _has_relation_action(value: dict[str, Any]) -> bool:
    return any(key in value for key in SUPPORTED_RELATION_ACTIONS)


def _has_non_primary_key_fields(value: dict[str, Any]) -> bool:
    return any(key not in PRIMARY_KEY_FIELDS for key in value.keys())


def normalize_relation_input(
    value: Any,
    relation: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    relation = relation or {}
    is_to_many = bool(relation.get("is_to_many", relation.get("isToMany", False)))

    if value is None:
        return {}

    if isinstance(value, dict):
        if _has_relation_action(value):
            return value

        pk_value = _extract_primary_key(value)
        if is_to_many:
            normalized: dict[str, Any] = {}
            if pk_value is not None:
                normalized["connect"] = [pk_value]
                if _has_non_primary_key_fields(value):
                    normalized["update"] = [value]
                return normalized
            return {"create": [value]}

        if pk_value is not None:
            if _has_non_primary_key_fields(value):
                return {"update": value}
            return {"connect": pk_value}
        return {"create": value}

    if isinstance(value, (list, tuple)):
        items = list(value)
        if not is_to_many:
            if len(items) != 1:
                raise GraphQLError(
                    "Singular relation inputs must provide exactly one value."
                )
            return normalize_relation_input(items[0], relation=relation)

        normalized: dict[str, Any] = {}
        connect_items: list[Any] = []
        create_items: list[dict[str, Any]] = []
        update_items: list[dict[str, Any]] = []

        for item in items:
            if isinstance(item, dict):
                if _has_relation_action(item):
                    raise GraphQLError(
                        "To-many relation lists must contain identifiers or plain "
                        "objects, not nested action payloads."
                    )
                pk_value = _extract_primary_key(item)
                if pk_value is None:
                    create_items.append(item)
                    continue
                connect_items.append(pk_value)
                if _has_non_primary_key_fields(item):
                    update_items.append(item)
            else:
                connect_items.append(item)

        if connect_items:
            normalized["connect"] = connect_items
        if create_items:
            normalized["create"] = create_items
        if update_items:
            normalized["update"] = update_items
        return normalized

    if is_to_many:
        return {"connect": [value]}
    return {"connect": value}
