"""Base utilities and helper functions for metadata extractors.

This module provides shared functionality used by all metadata extractors,
including permission building, JSON serialization, translation helpers,
and cache key generation.
"""

import logging
from typing import Any, Optional

from django.apps import apps
from django.db import models
from django.utils.encoding import force_str

from ..types import (
    FieldPermissionMetadata,
    ModelPermissionMatrix,
)

logger = logging.getLogger(__name__)


def _is_fsm_field_instance(field: Any) -> bool:
    """
    Detect whether a field is provided by django_fsm.FSMField.

    This check is done without forcing the dependency at import time.

    Args:
        field: The Django model field to check.

    Returns:
        True if the field is an FSMField instance, False otherwise.
    """
    try:
        from django_fsm import FSMField

        return isinstance(field, FSMField)
    except Exception:
        return False


def _relationship_cardinality(
    is_reverse: bool, many_to_many: bool, one_to_one: bool, foreign_key: bool
) -> str:
    """
    Determine the cardinality string for a relationship.

    Args:
        is_reverse: Whether this is a reverse relationship.
        many_to_many: Whether this is a many-to-many relationship.
        one_to_one: Whether this is a one-to-one relationship.
        foreign_key: Whether this is a foreign key relationship.

    Returns:
        A string describing the cardinality: 'many_to_many', 'one_to_one',
        'one_to_many', 'many_to_one', or 'unknown'.
    """
    if many_to_many:
        return "many_to_many"
    if one_to_one:
        return "one_to_one"
    if foreign_key:
        return "one_to_many" if is_reverse else "many_to_one"
    return "unknown"


def _build_field_permission_snapshot(
    user,
    model_class: type[models.Model],
    field_name: str,
) -> Optional[FieldPermissionMetadata]:
    """
    Build a permission snapshot for a field.

    This function evaluates the current user's permissions for a specific
    field on a model, returning visibility and access level information.

    Args:
        user: The Django user to check permissions for.
        model_class: The Django model class containing the field.
        field_name: The name of the field to check permissions for.

    Returns:
        A FieldPermissionMetadata dataclass with permission details,
        or a restricted snapshot if the user is not authenticated.
    """
    # Lazy imports to avoid AppRegistryNotReady
    from rail_django.security.field_permissions import (
        FieldAccessLevel,
        FieldContext,
        FieldVisibility,
        field_permission_manager,
    )

    if not user or not getattr(user, "is_authenticated", False):
        return FieldPermissionMetadata(
            can_read=False,
            can_write=False,
            visibility=FieldVisibility.HIDDEN.value,
            access_level=FieldAccessLevel.NONE.value,
            reason="Authentification requise.",
        )

    context = FieldContext(
        user=user,
        model_class=model_class,
        field_name=field_name,
        operation_type="read",
    )
    access_level = field_permission_manager.get_field_access_level(context)
    visibility, mask_value = field_permission_manager.get_field_visibility(context)
    can_read = access_level in (
        FieldAccessLevel.READ,
        FieldAccessLevel.WRITE,
        FieldAccessLevel.ADMIN,
    )
    can_write = access_level in (FieldAccessLevel.WRITE, FieldAccessLevel.ADMIN)
    reason = None if can_read else "Permission insuffisante pour consulter ce champ."
    return FieldPermissionMetadata(
        can_read=can_read,
        can_write=can_write,
        visibility=visibility.value,
        access_level=access_level.value,
        mask_value=mask_value,
        reason=reason,
    )


def _build_model_permission_matrix(
    model: type[models.Model], user
) -> ModelPermissionMatrix:
    """
    Compute CRUD permissions for a model and user.

    This function evaluates the current user's permissions for standard
    CRUD operations on a model, checking both Django permissions and
    any custom guards defined in GraphQLMeta.

    Args:
        model: The Django model class to check permissions for.
        user: The Django user to check permissions for.

    Returns:
        A ModelPermissionMatrix dataclass with boolean flags for each
        operation and optional denial reasons.
    """
    # Lazy import
    from rail_django.utils.graphql_meta import get_model_graphql_meta

    app_label = model._meta.app_label
    model_lower = model._meta.model_name
    operations = {
        "create": f"{app_label}.add_{model_lower}",
        "update": f"{app_label}.change_{model_lower}",
        "delete": f"{app_label}.delete_{model_lower}",
        "read": f"{app_label}.view_{model_lower}",
        "list": f"{app_label}.view_{model_lower}",
        "history": f"{app_label}.view_{model_lower}",
    }
    guard_map = {
        "create": "create",
        "update": "update",
        "delete": "delete",
        "read": "retrieve",
        "list": "list",
        "history": "history",
    }
    reasons: dict[str, Optional[str]] = {}

    if not user or not getattr(user, "is_authenticated", False):
        for op in operations.keys():
            reasons[op] = "Authentification requise."
        return ModelPermissionMatrix(
            can_create=False,
            can_update=False,
            can_delete=False,
            can_read=False,
            can_list=False,
            reasons=reasons,
        )

    guard_results: dict[str, dict[str, Any]] = {}
    try:
        graphql_meta = get_model_graphql_meta(model)
    except Exception:
        graphql_meta = None

    if graphql_meta:
        for guard_name in set(guard_map.values()):
            guard_results[guard_name] = graphql_meta.describe_operation_guard(
                guard_name, user=user
            )

    def evaluate(op: str) -> bool:
        allowed = user.has_perm(operations[op])
        reason = None if allowed else f"Permission {operations[op]} requise."
        guard_name = guard_map.get(op)
        guard_info = guard_results.get(guard_name) if guard_name else None
        if guard_info:
            guard_allowed = guard_info.get("allowed", True)
            if guard_allowed:
                allowed = True
                reason = None
            else:
                allowed = False
                reason = guard_info.get("reason") or reason
        if not allowed and reason:
            reasons[op] = reason
        return allowed

    matrix = ModelPermissionMatrix(
        can_create=evaluate("create"),
        can_update=evaluate("update"),
        can_delete=evaluate("delete"),
        can_read=evaluate("read"),
        can_list=evaluate("list"),
        can_history=evaluate("history"),
        reasons=reasons,
    )
    return matrix


class JsonSerializerMixin:
    """Mixin providing JSON serialization utilities for extractors."""

    def _json_safe_value(self, value: Any) -> Any:
        """
        Convert Django/Python values to JSON-serializable primitives.

        Handles dates, datetimes, times, Decimals, lazy translations,
        and nested containers.

        Args:
            value: Any Python value to convert.

        Returns:
            A JSON-serializable primitive (str, int, float, bool, None,
            list, or dict).
        """
        from datetime import date, datetime, time
        from decimal import Decimal

        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date, time)):
            try:
                return value.isoformat()
            except Exception:
                return force_str(value)
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {
                force_str(key): self._json_safe_value(val) for key, val in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe_value(val) for val in value]
        return force_str(value)

    def _sanitize_action_payload(self, payload: Any) -> Any:
        """
        Strip callables and non-serializable values from action metadata.

        Args:
            payload: The action payload to sanitize.

        Returns:
            A sanitized payload suitable for JSON serialization.
        """
        if payload is None:
            return None
        if isinstance(payload, dict):
            cleaned: dict[str, Any] = {}
            for key, val in payload.items():
                if callable(val):
                    continue
                cleaned[force_str(key)] = self._sanitize_action_payload(val)
            return cleaned
        if isinstance(payload, (list, tuple, set)):
            return [
                self._sanitize_action_payload(val)
                for val in payload
                if not callable(val)
            ]
        return self._json_safe_value(payload)

    def _to_json_safe(self, value: Any) -> Any:
        """
        Convert Python/Django values into JSON-serializable primitives.

        Alias for _json_safe_value with additional error handling.

        Args:
            value: Any Python value to convert.

        Returns:
            A JSON-serializable value.
        """
        try:
            return self._json_safe_value(value)
        except Exception:
            return str(value)


class TranslationMixin:
    """Mixin providing filter help text translation utilities."""

    def _translate_help_text_to_french(
        self, original_text: str, verbose_name: str
    ) -> str:
        """
        Translate help text to French using field verbose_name.

        Args:
            original_text: Original English help text or lookup expression.
            verbose_name: Field verbose name to use in translation.

        Returns:
            French translated help text.
        """
        translations = {
            "exact": f"Correspondance exacte pour {verbose_name}",
            "iexact": f"Correspondance exacte insensible à la casse pour {verbose_name}",
            "contains": f"Contient le texte dans {verbose_name}",
            "icontains": f"Contient le texte (insensible à la casse) dans {verbose_name}",
            "startswith": f"Commence par le texte dans {verbose_name}",
            "istartswith": f"Commence par le texte (insensible à la casse) dans {verbose_name}",
            "endswith": f"Se termine par le texte dans {verbose_name}",
            "iendswith": f"Se termine par le texte (insensible à la casse) dans {verbose_name}",
            "in": f"Correspond à l'une des valeurs fournies pour {verbose_name}",
            "gt": f"Supérieur à la valeur pour {verbose_name}",
            "gte": f"Supérieur ou égal à la valeur pour {verbose_name}",
            "lt": f"Inférieur à la valeur pour {verbose_name}",
            "lte": f"Inférieur ou égal à la valeur pour {verbose_name}",
            "range": f"Valeur dans la plage pour {verbose_name}",
            "isnull": f"Vérifier si {verbose_name} est nul",
            "today": f"Filtrer pour la date d'aujourd'hui dans {verbose_name}",
            "yesterday": f"Filtrer pour la date d'hier dans {verbose_name}",
            "this_week": f"Filtrer pour les dates de cette semaine dans {verbose_name}",
            "this_month": f"Filtrer pour les dates de ce mois dans {verbose_name}",
            "this_year": f"Filtrer pour les dates de cette année dans {verbose_name}",
            "past_week": f"Filtrer pour les dates de la semaine dernière dans {verbose_name}",
            "past_month": f"Filtrer pour les dates du mois dernier dans {verbose_name}",
            "past_year": f"Filtrer pour les dates de l'année dernière dans {verbose_name}",
            "last_week": f"Filtrer pour les dates de la semaine dernière dans {verbose_name}",
            "last_month": f"Filtrer pour les dates du mois dernier dans {verbose_name}",
            "last_year": f"Filtrer pour les dates de l'année dernière dans {verbose_name}",
            "year": f"Filtrer par année pour {verbose_name}",
            "month": f"Filtrer par mois pour {verbose_name}",
            "day": f"Filtrer par jour pour {verbose_name}",
        }

        # Normalize for matching
        original_lc = original_text.lower()

        # Prioritize relative date/time lookups
        for rel_lookup in (
            "today",
            "yesterday",
            "this_week",
            "this_month",
            "this_year",
            "past_week",
            "past_month",
            "past_year",
            "last_week",
            "last_month",
            "last_year",
            "year",
            "month",
            "day",
        ):
            if rel_lookup in original_lc:
                return translations[rel_lookup]

        # Then match common generic lookups
        for gen_lookup in (
            "exact",
            "iexact",
            "contains",
            "icontains",
            "startswith",
            "istartswith",
            "endswith",
            "iendswith",
            "in",
            "gt",
            "gte",
            "lt",
            "lte",
            "range",
            "isnull",
        ):
            if gen_lookup in original_lc:
                return translations[gen_lookup]

        # Fallback: basic translation
        if "exact match" in original_lc:
            return f"Correspondance exacte pour {verbose_name}"
        elif "contains" in original_lc:
            return f"Contient le texte dans {verbose_name}"
        elif "greater than" in original_lc:
            return f"Supérieur à la valeur pour {verbose_name}"
        elif "less than" in original_lc:
            return f"Inférieur à la valeur pour {verbose_name}"
        else:
            return f"Filtre pour {verbose_name}"


class BaseMetadataExtractor(JsonSerializerMixin, TranslationMixin):
    """
    Base class for metadata extractors with common functionality.

    Provides JSON serialization utilities, translation helpers,
    and shared initialization logic.
    """

    def __init__(self, schema_name: str = "default", max_depth: int = 1):
        """
        Initialize the base metadata extractor.

        Args:
            schema_name: Name of the schema configuration to use.
            max_depth: Maximum depth for nested related model metadata.
        """
        self.schema_name = schema_name
        self.max_depth = max_depth

    def _has_field_permission(self, user, model: type, field_name: str) -> bool:
        """
        Check if user has permission to access a specific field.

        Args:
            user: Django user instance.
            model: Django model class.
            field_name: Name of the field to check.

        Returns:
            True if user has permission to access the field.
        """
        from django.contrib.auth.models import AnonymousUser

        if isinstance(user, AnonymousUser):
            return False

        # Check basic view permission for the model
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        view_permission = f"{app_label}.view_{model_name}"

        try:
            return user.has_perm(view_permission)
        except Exception:
            return False

    def _get_related_model_name(self, model, field_path: str) -> Optional[str]:
        """
        Get the related model name for a nested field path.

        Args:
            model: Base Django model.
            field_path: Field path like 'author__username'.

        Returns:
            Related model name or None.
        """
        try:
            field_parts = field_path.split("__")
            current_model = model

            for field_name in field_parts[:-1]:
                field = current_model._meta.get_field(field_name)
                if hasattr(field, "related_model"):
                    current_model = field.related_model
                else:
                    return None

            return current_model.__name__
        except Exception:
            return None


__all__ = [
    "_is_fsm_field_instance",
    "_relationship_cardinality",
    "_build_field_permission_snapshot",
    "_build_model_permission_matrix",
    "JsonSerializerMixin",
    "TranslationMixin",
    "BaseMetadataExtractor",
]
