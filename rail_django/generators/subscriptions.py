"""
Subscription generation for GraphQL auto-generation.

Auto-generated subscriptions rely on channels-graphql-ws and emit
per-model created/updated/deleted events with optional filtering.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
from typing import Any, Dict, Iterable, Optional, Tuple, Type

import graphene
from django.contrib.auth.models import AnonymousUser
from django.db import models
from graphql import GraphQLError

from ..core.meta import get_model_graphql_meta
from ..core.settings import SchemaSettings, SubscriptionGeneratorSettings
from ..security.field_permissions import mask_sensitive_fields
from ..subscriptions.registry import register_subscription
from .filters import AdvancedFilterGenerator
from .types import TypeGenerator

logger = logging.getLogger(__name__)

_GROUP_NAME_SAFE_RE = re.compile(r"[^0-9A-Za-z_.-]")


def _get_subscription_base() -> Type:
    try:
        import channels_graphql_ws  # type: ignore
    except Exception as exc:
        raise ImportError(
            "channels-graphql-ws is required for subscriptions. "
            "Install it with: pip install channels-graphql-ws"
        ) from exc

    return channels_graphql_ws.Subscription


def _sanitize_group_name(value: str, max_length: int = 90) -> str:
    safe = _GROUP_NAME_SAFE_RE.sub("_", value)
    if len(safe) <= max_length:
        return safe
    digest = hashlib.sha1(safe.encode("utf-8")).hexdigest()[:10]
    trimmed = safe[: max_length - 11]
    return f"{trimmed}-{digest}"


def _build_group_name(schema_name: str, model_label: str, event: str) -> str:
    base = f"rail_sub:{schema_name}:{model_label}:{event}"
    return _sanitize_group_name(base)


def _copy_filter_payload(filters: Any) -> Optional[Dict[str, Any]]:
    if not filters:
        return None
    if isinstance(filters, dict):
        return copy.deepcopy(filters)
    try:
        return copy.deepcopy(dict(filters))
    except Exception:
        return None


def _apply_field_masks(
    instance: models.Model, info: graphene.ResolveInfo, model: Type[models.Model]
) -> models.Model:
    context_user = getattr(getattr(info, "context", None), "user", None)
    if context_user is None:
        context_user = AnonymousUser()
    if getattr(context_user, "is_superuser", False):
        return instance

    field_defs = list(instance._meta.concrete_fields)
    snapshot: Dict[str, Any] = {}

    for field in field_defs:
        if field.is_relation and (field.many_to_one or field.one_to_one):
            val = getattr(instance, field.attname, None)
        else:
            val = getattr(instance, field.name, None)
        snapshot[field.name] = val

    masked = mask_sensitive_fields(snapshot, context_user, model, instance=instance)
    for field in field_defs:
        name = field.name
        attname = getattr(field, "attname", name)
        if name in masked:
            instance.__dict__[attname] = masked[name]
        else:
            instance.__dict__[attname] = None

    return instance


def _coerce_iterable(value: Any) -> Iterable:
    if value is None:
        return []
    if hasattr(value, "all") and callable(value.all):
        try:
            return list(value.all())
        except Exception:
            return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _resolve_values(obj: Any, path_parts: Iterable[str]) -> list:
    values = [obj]
    for part in path_parts:
        next_values = []
        for value in values:
            if value is None:
                continue
            for item in _coerce_iterable(value):
                try:
                    attr = getattr(item, part)
                except Exception:
                    attr = None
                if hasattr(attr, "all") and callable(attr.all):
                    try:
                        next_values.extend(list(attr.all()))
                    except Exception:
                        continue
                else:
                    next_values.append(attr)
        values = next_values
    return values


def _compare_value(value: Any, lookup: str, expected: Any) -> bool:
    if lookup == "exact":
        return value == expected
    if lookup == "iexact":
        if value is None or expected is None:
            return False
        return str(value).lower() == str(expected).lower()
    if lookup in {"contains", "icontains"}:
        if value is None or expected is None:
            return False
        haystack = str(value)
        needle = str(expected)
        if lookup == "icontains":
            haystack = haystack.lower()
            needle = needle.lower()
        return needle in haystack
    if lookup in {"startswith", "istartswith"}:
        if value is None or expected is None:
            return False
        haystack = str(value)
        needle = str(expected)
        if lookup == "istartswith":
            haystack = haystack.lower()
            needle = needle.lower()
        return haystack.startswith(needle)
    if lookup in {"endswith", "iendswith"}:
        if value is None or expected is None:
            return False
        haystack = str(value)
        needle = str(expected)
        if lookup == "iendswith":
            haystack = haystack.lower()
            needle = needle.lower()
        return haystack.endswith(needle)
    if lookup == "in":
        if expected is None:
            return False
        try:
            return value in expected
        except Exception:
            return False
    if lookup == "isnull":
        is_null = value is None
        return bool(expected) == is_null
    if lookup in {"gt", "gte", "lt", "lte"}:
        if value is None or expected is None:
            return False
        if lookup == "gt":
            return value > expected
        if lookup == "gte":
            return value >= expected
        if lookup == "lt":
            return value < expected
        return value <= expected
    if lookup == "range":
        if value is None or expected is None:
            return False
        try:
            lower, upper = expected
        except Exception:
            return False
        return lower <= value <= upper
    if lookup == "year":
        return getattr(value, "year", None) == expected
    if lookup == "month":
        return getattr(value, "month", None) == expected
    if lookup == "day":
        return getattr(value, "day", None) == expected
    if lookup in {"regex", "iregex"}:
        if value is None or expected is None:
            return False
        flags = re.IGNORECASE if lookup == "iregex" else 0
        try:
            return re.search(str(expected), str(value), flags) is not None
        except Exception:
            return False
    if lookup in {"has_key", "has_keys", "has_any_keys"}:
        if not isinstance(value, dict):
            return False
        if lookup == "has_key":
            return expected in value
        if lookup == "has_keys":
            return all(key in value for key in (expected or []))
        return any(key in value for key in (expected or []))
    return False


def _evaluate_filter_dict(instance: Any, filter_dict: Dict[str, Any]) -> bool:
    if not filter_dict:
        return True

    if "AND" in filter_dict:
        and_items = filter_dict.get("AND") or []
        if not all(_evaluate_filter_dict(instance, item) for item in and_items):
            return False

    if "OR" in filter_dict:
        or_items = filter_dict.get("OR") or []
        if or_items and not any(
            _evaluate_filter_dict(instance, item) for item in or_items
        ):
            return False

    if "NOT" in filter_dict:
        not_item = filter_dict.get("NOT") or {}
        if _evaluate_filter_dict(instance, not_item):
            return False

    for key, expected in filter_dict.items():
        if key in {"AND", "OR", "NOT"}:
            continue
        parts = key.split("__")
        lookup = "exact"
        if parts[-1] in {
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
            "year",
            "month",
            "day",
            "regex",
            "iregex",
            "has_key",
            "has_keys",
            "has_any_keys",
        }:
            lookup = parts.pop()

        field_path = "__".join(parts)
        if field_path.endswith("_count"):
            base_field = field_path[: -len("_count")]
            values = _resolve_values(instance, base_field.split("__")) if base_field else []
            count_value = len(values)
            if not _compare_value(count_value, lookup, expected):
                return False
            continue

        values = _resolve_values(instance, parts)
        if lookup == "isnull" and not values:
            values = [None]

        matched = any(_compare_value(value, lookup, expected) for value in values)
        if not matched:
            return False

    return True


def _matches_filters(
    instance: models.Model,
    model: Type[models.Model],
    filters: Optional[Dict[str, Any]],
    filter_generator: AdvancedFilterGenerator,
    *,
    use_db: bool,
) -> bool:
    if not filters:
        return True

    if use_db and getattr(instance, "pk", None) is not None:
        try:
            queryset = model._default_manager.filter(pk=instance.pk)
            payload = _copy_filter_payload(filters)
            if payload:
                queryset = filter_generator.apply_complex_filters(queryset, payload)
            return queryset.exists()
        except Exception as exc:
            logger.warning(
                "Subscription filter evaluation failed for %s: %s",
                model.__name__,
                exc,
            )

    try:
        return _evaluate_filter_dict(instance, _copy_filter_payload(filters) or {})
    except Exception as exc:
        logger.warning(
            "Fallback subscription filter evaluation failed for %s: %s",
            model.__name__,
            exc,
        )
    return False


class SubscriptionGenerator:
    """
    Generates GraphQL subscriptions for Django models.
    """

    def __init__(
        self,
        type_generator: TypeGenerator,
        settings: Optional[SubscriptionGeneratorSettings] = None,
        schema_name: str = "gql",
    ) -> None:
        self.type_generator = type_generator
        self.schema_name = schema_name
        self.settings = (
            settings if settings is not None else SubscriptionGeneratorSettings.from_schema(schema_name)
        )
        self.filter_generator = AdvancedFilterGenerator(schema_name=schema_name)

    def _ensure_authentication(self, info: graphene.ResolveInfo) -> None:
        # Determine effective schema name (priority: context > generator default)
        schema_name = getattr(info.context, "schema_name", None)
        if not schema_name and isinstance(info.context, dict):
            schema_name = info.context.get("schema_name")
        
        # Check scope if available (Channels)
        if not schema_name and hasattr(info.context, "scope"):
             schema_name = info.context.scope.get("schema_name")
        elif not schema_name and isinstance(info.context, dict) and "scope" in info.context:
             schema_name = info.context["scope"].get("schema_name")

        if not schema_name:
            schema_name = self.schema_name

        schema_settings = SchemaSettings.from_schema(schema_name)

        if not schema_settings.authentication_required:
            return

        user = getattr(getattr(info, "context", None), "user", None)
        if not user or not user.is_authenticated:
            raise GraphQLError("Authentication required")

    def _normalize_model_filters(self) -> Tuple[set, set]:
        include_models = self.settings.include_models or []
        exclude_models = self.settings.exclude_models or []

        def _normalize(values):
            normalized = set()
            for value in values:
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    normalized.add(text.lower())
            return normalized

        return _normalize(include_models), _normalize(exclude_models)

    def _model_tokens(self, model: Type[models.Model]) -> set:
        app_label = getattr(model._meta, "app_label", "")
        model_name = model.__name__
        label = getattr(model._meta, "label", f"{app_label}.{model_name}")
        label_lower = getattr(model._meta, "label_lower", f"{app_label}.{model_name}")

        tokens = {
            label,
            label_lower,
            f"{app_label}.{model_name}",
            f"{app_label}.{model_name.lower()}",
            model_name,
            model_name.lower(),
        }
        return {token.lower() for token in tokens if token}

    def _model_is_allowed(self, model: Type[models.Model]) -> bool:
        include_set, exclude_set = self._normalize_model_filters()
        tokens = self._model_tokens(model)

        if include_set and not (tokens & include_set):
            return False
        if exclude_set and (tokens & exclude_set):
            return False
        return True

    def _build_subscription_class(
        self,
        model: Type[models.Model],
        model_type: Type[graphene.ObjectType],
        event: str,
        filter_input: Optional[Type[graphene.InputObjectType]],
    ) -> Type:
        base_class = _get_subscription_base()
        group_name = _build_group_name(
            self.schema_name, model._meta.label_lower, event
        )
        graphql_meta = get_model_graphql_meta(model)
        schema_name = self.schema_name
        use_db_filters = event != "deleted"

        arguments = {}
        if filter_input is not None and self.settings.enable_filters:
            arguments["filters"] = graphene.Argument(
                filter_input,
                required=False,
                description="Filter events using model field lookups.",
            )

        arguments_type = type("Arguments", (), arguments)
        skip_marker = getattr(base_class, "SKIP", None)

        def _skip():
            return skip_marker

        def subscribe(root, info, filters: Optional[Dict[str, Any]] = None, **kwargs):
            self._ensure_authentication(info)
            graphql_meta.ensure_operation_access("list", info=info)
            graphql_meta.ensure_operation_access("subscribe", info=info)
            return [group_name]

        def publish(payload, info, filters: Optional[Dict[str, Any]] = None, **kwargs):
            instance = None
            if isinstance(payload, dict):
                instance = payload.get("instance")
            if instance is None:
                return _skip()

            try:
                self._ensure_authentication(info)
            except GraphQLError:
                return _skip()

            try:
                graphql_meta.ensure_operation_access(
                    "retrieve", info=info, instance=instance
                )
                graphql_meta.ensure_operation_access(
                    "subscribe", info=info, instance=instance
                )
            except GraphQLError:
                return _skip()

            if not _matches_filters(
                instance,
                model,
                filters,
                self.filter_generator,
                use_db=use_db_filters,
            ):
                return _skip()

            instance = _apply_field_masks(instance, info, model)
            return {
                "event": event,
                "node": instance,
                "id": getattr(instance, "pk", None),
            }

        class_name = f"{model.__name__}{event.title()}Subscription"
        attrs = {
            "__doc__": f"{model.__name__} {event} subscription.",
            "Arguments": arguments_type,
            "event": graphene.String(required=True),
            "node": graphene.Field(model_type),
            "id": graphene.ID(required=True),
            "schema_name": schema_name,
            "model_class": model,
            "event_type": event,
            "group_name": group_name,
            "subscribe": staticmethod(subscribe),
            "publish": staticmethod(publish),
        }
        return type(class_name, (base_class,), attrs)

    def generate_model_subscriptions(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.Field]:
        # Check global enabled flag
        if not self.settings.enable_subscriptions:
            return {}

        # Check model allow/deny lists from settings
        if not self._model_is_allowed(model):
            return {}

        # Check GraphQLMeta configuration
        graphql_meta = get_model_graphql_meta(model)
        meta_subs = getattr(graphql_meta, "subscriptions", None)

        # If meta.subscriptions is explicitly False, disable
        if meta_subs is False:
            return {}

        # Default event configuration from settings
        event_config = {
            "created": self.settings.enable_create,
            "updated": self.settings.enable_update,
            "deleted": self.settings.enable_delete,
        }

        # Override with GraphQLMeta if present
        if meta_subs is not None:
            if isinstance(meta_subs, (list, tuple)):
                # ["create", "update"]
                # Map "create" -> "created", "update" -> "updated", etc. if needed
                # But let's assume users use "created", "updated", "deleted" or "create", "update", "delete"
                subs_set = {str(s).lower() for s in meta_subs}
                
                # Normalize aliases
                if "create" in subs_set: subs_set.add("created")
                if "update" in subs_set: subs_set.add("updated")
                if "delete" in subs_set: subs_set.add("deleted")

                event_config["created"] = "created" in subs_set
                event_config["updated"] = "updated" in subs_set
                event_config["deleted"] = "deleted" in subs_set
            elif isinstance(meta_subs, dict):
                # {"create": True, "update": False}
                # Normalize keys
                normalized = {}
                for k, v in meta_subs.items():
                    k_lower = str(k).lower()
                    if k_lower == "create": k_lower = "created"
                    if k_lower == "update": k_lower = "updated"
                    if k_lower == "delete": k_lower = "deleted"
                    normalized[k_lower] = bool(v)
                
                if "created" in normalized: event_config["created"] = normalized["created"]
                if "updated" in normalized: event_config["updated"] = normalized["updated"]
                if "deleted" in normalized: event_config["deleted"] = normalized["deleted"]
            elif meta_subs is True:
                 # Enable all
                 event_config["created"] = True
                 event_config["updated"] = True
                 event_config["deleted"] = True

        model_type = self.type_generator.generate_object_type(model)
        filter_input = self.filter_generator.generate_complex_filter_input(model)
        subscriptions: Dict[str, graphene.Field] = {}

        for event, enabled in event_config.items():
            if not enabled:
                continue
            subscription_class = self._build_subscription_class(
                model, model_type, event, filter_input
            )
            field_name = f"{model.__name__.lower()}_{event}"
            subscriptions[field_name] = subscription_class.Field()
            register_subscription(
                self.schema_name, model._meta.label_lower, event, subscription_class
            )

        return subscriptions

    def generate_all_subscriptions(
        self, models_list: Iterable[Type[models.Model]]
    ) -> Dict[str, graphene.Field]:
        subscriptions: Dict[str, graphene.Field] = {}
        if not self.settings.enable_subscriptions:
            return subscriptions
        for model in models_list:
            if not self._model_is_allowed(model):
                continue
            subscriptions.update(self.generate_model_subscriptions(model))
        return subscriptions
