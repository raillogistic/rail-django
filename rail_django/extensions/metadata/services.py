"""Public, permission-aware metadata discovery services."""

from __future__ import annotations

from typing import Any, Optional

from django.apps import apps
from graphql import GraphQLError

from ...core.meta import get_model_graphql_meta
from .extractor import ModelSchemaExtractor


def user_can_discover_model(model, user: Any) -> bool:
    """Return whether ``user`` may discover a Django model through metadata."""
    if user and getattr(user, "is_superuser", False):
        return True

    states: list[dict] = []
    try:
        graphql_meta = get_model_graphql_meta(model)
        describe = getattr(graphql_meta, "describe_operation_guard", None)
        if callable(describe):
            for operation in ("list", "retrieve"):
                try:
                    state = describe(operation, user=user, instance=None)
                except Exception:
                    continue
                if isinstance(state, dict):
                    states.append(state)
    except Exception:
        pass

    guarded_states = [state for state in states if state.get("guarded")]
    guarded_allows = any(state.get("allowed", False) for state in guarded_states)
    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    if not is_authenticated:
        return guarded_allows
    if guarded_states and not guarded_allows:
        return False

    has_perm = getattr(user, "has_perm", None)
    if callable(has_perm):
        permission = f"{model._meta.app_label}.view_{model._meta.model_name}"
        try:
            if has_perm(permission):
                return True
        except Exception:
            pass
    return guarded_allows


def get_model_schema_for_user(
    app_label: str,
    model_name: str,
    user: Any,
    *,
    schema_name: str = "default",
    object_id: Optional[str] = None,
    include_sections: Optional[set[str]] = None,
    include_section_subfields: Optional[dict[str, set[str]]] = None,
) -> dict:
    """Return the same secured model contract used by ``modelSchema``."""
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError as exc:
        raise GraphQLError(f"Model '{app_label}.{model_name}' not found.") from exc
    if not user_can_discover_model(model, user):
        raise GraphQLError("Access denied")
    return ModelSchemaExtractor(schema_name=schema_name).extract(
        app_label,
        model_name,
        user=user,
        object_id=object_id,
        include_sections=include_sections,
        include_section_subfields=include_section_subfields,
    )


def list_available_models_for_user(user: Any, app_label: str | None = None) -> list[dict]:
    """List models discoverable by ``user`` using the metadata security policy."""
    results = []
    for model in apps.get_models():
        if app_label and model._meta.app_label != app_label:
            continue
        if model._meta.app_label in {"admin", "auth", "contenttypes", "sessions"}:
            continue
        if not user_can_discover_model(model, user):
            continue
        results.append(
            {
                "app": model._meta.app_label,
                "model": model.__name__,
                "verbose_name": str(model._meta.verbose_name),
                "verbose_name_plural": str(model._meta.verbose_name_plural),
            }
        )
    return results


__all__ = [
    "get_model_schema_for_user",
    "list_available_models_for_user",
    "user_can_discover_model",
]
