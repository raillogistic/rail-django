"""
SubscriptionGenerator implementation.
"""

import logging
from typing import Any, Dict, Iterable, Optional, Type

import graphene
from django.db import models
from graphql import GraphQLError

from ...core.meta import get_model_graphql_meta
from ...core.settings import SchemaSettings, SubscriptionGeneratorSettings
from ...extensions.subscriptions.registry import register_subscription
from ..filters import AdvancedFilterGenerator, NestedFilterInputGenerator, NestedFilterApplicator
from ..types import TypeGenerator

from .utils import (
    _get_subscription_base,
    _build_group_name,
    _get_context_user,
    _build_instance_from_payload,
    _apply_field_masks,
)
from .evaluator import _matches_filters

logger = logging.getLogger(__name__)


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
        self.nested_filter_generator = NestedFilterInputGenerator(schema_name=schema_name)
        self.nested_filter_applicator = NestedFilterApplicator(schema_name=schema_name)

    def _ensure_authentication(self, info: graphene.ResolveInfo) -> None:
        schema_name = getattr(info.context, "schema_name", None)
        if not schema_name and isinstance(info.context, dict):
            schema_name = info.context.get("schema_name")
        if not schema_name and hasattr(info.context, "scope"):
             schema_name = info.context.scope.get("schema_name")
        elif not schema_name and isinstance(info.context, dict) and "scope" in info.context:
             schema_name = info.context["scope"].get("schema_name")

        if not schema_name:
            schema_name = self.schema_name

        schema_settings = SchemaSettings.from_schema(schema_name)
        if not schema_settings.authentication_required:
            return

        user = _get_context_user(info)
        if not user or not user.is_authenticated:
            raise GraphQLError("Authentication required")

    def _model_is_allowed(self, model: type[models.Model]) -> bool:
        include_models = self.settings.include_models or []
        exclude_models = self.settings.exclude_models or []

        def _normalize(values):
            normalized = set()
            for v in values:
                if v is None: continue
                normalized.add(str(v).strip().lower())
            return normalized

        include_set, exclude_set = _normalize(include_models), _normalize(exclude_models)
        app_label = getattr(model._meta, "app_label", "")
        model_name = model.__name__
        tokens = {
            getattr(model._meta, "label", f"{app_label}.{model_name}"),
            getattr(model._meta, "label_lower", f"{app_label}.{model_name}"),
            f"{app_label}.{model_name}",
            f"{app_label}.{model_name.lower()}",
            model_name,
            model_name.lower(),
        }
        tokens = {t.lower() for t in tokens if t}

        if include_set:
            if not (tokens & include_set): return False
        elif not getattr(self.settings, "discover_models", True):
            return False

        if exclude_set and (tokens & exclude_set): return False
        return True

    def _build_subscription_class(
        self,
        model: type[models.Model],
        model_type: type[graphene.ObjectType],
        event: str,
        filter_input: Optional[type[graphene.InputObjectType]],
    ) -> tuple[type, dict[str, graphene.Argument]]:
        base_class = _get_subscription_base()
        group_name = _build_group_name(self.schema_name, model._meta.label_lower, event)
        graphql_meta = get_model_graphql_meta(model)
        schema_name = self.schema_name
        use_db_filters = event != "deleted"

        arguments = {}
        if filter_input is not None and self.settings.enable_filters:
            arguments["filters"] = graphene.Argument(
                filter_input, required=False, description="Filter events using model field lookups.",
            )

        skip_marker = getattr(base_class, "SKIP", None)

        def _skip(): return skip_marker

        def subscribe(root, info, filters: Optional[dict[str, Any]] = None, **kwargs):
            self._ensure_authentication(info)
            graphql_meta.ensure_operation_access("list", info=info)
            graphql_meta.ensure_operation_access("subscribe", info=info)
            return [group_name]

        def publish(payload, info, filters: Optional[dict[str, Any]] = None, **kwargs):
            # Check if we are in publication phase
            # If not (e.g. initial subscribe call), return None
            if not getattr(info.context, "is_publication", False):
                return None

            instance = _build_instance_from_payload(model, payload)
            if instance is None: return _skip()
            try: self._ensure_authentication(info)
            except GraphQLError: return _skip()
            try:
                graphql_meta.ensure_operation_access("retrieve", info=info, instance=instance)
                graphql_meta.ensure_operation_access("subscribe", info=info, instance=instance)
            except GraphQLError: return _skip()

            if not _matches_filters(instance, model, filters, self.nested_filter_applicator, use_db=use_db_filters):
                return _skip()

            instance = _apply_field_masks(instance, info, model)
            return {
                "event": event,
                "node": instance,
                "id": str(getattr(instance, "pk", None) or ""),
            }

        class_name = f"{model.__name__}{event.title()}Subscription"
        attrs = {
            "__doc__": f"{model.__name__} {event} subscription.",
            "event": graphene.String(required=True),
            "node": graphene.Field(model_type),
            "id": graphene.ID(required=True),
            "schema_name": schema_name,
            "model_class": model,
            "event_type": event,
            "group_name": group_name,
            "resolve_event": lambda root, info, **kwargs: root.get("event"),
            "resolve_node": lambda root, info, **kwargs: root.get("node"),
            "resolve_id": lambda root, info, **kwargs: root.get("id"),
        }
        
        # We store 'subscribe' and 'publish' as attributes for the consumer to find
        subscription_class = type(class_name, (base_class,), attrs)
        subscription_class.subscribe = staticmethod(subscribe)
        subscription_class.publish = staticmethod(publish)
        
        return subscription_class, arguments

    def generate_model_subscriptions(self, model: type[models.Model]) -> dict[str, graphene.Field]:
        if not self.settings.enable_subscriptions or not self._model_is_allowed(model): return {}
        graphql_meta = get_model_graphql_meta(model)
        meta_subs = getattr(graphql_meta, "subscriptions", None)
        if meta_subs is False: return {}

        event_config = {"created": self.settings.enable_create, "updated": self.settings.enable_update, "deleted": self.settings.enable_delete}
        if meta_subs is not None:
            if isinstance(meta_subs, (list, tuple)):
                subs_set = {str(s).lower() for s in meta_subs}
                if "create" in subs_set: subs_set.add("created")
                if "update" in subs_set: subs_set.add("updated")
                if "delete" in subs_set: subs_set.add("deleted")
                event_config["created"] = "created" in subs_set
                event_config["updated"] = "updated" in subs_set
                event_config["deleted"] = "deleted" in subs_set
            elif isinstance(meta_subs, dict):
                normalized = {}
                for k, v in meta_subs.items():
                    k_l = str(k).lower()
                    if k_l == "create": k_l = "created"
                    elif k_l == "update": k_l = "updated"
                    elif k_l == "delete": k_l = "deleted"
                    normalized[k_l] = bool(v)
                if "created" in normalized: event_config["created"] = normalized["created"]
                if "updated" in normalized: event_config["updated"] = normalized["updated"]
                if "deleted" in normalized: event_config["deleted"] = normalized["deleted"]
            elif meta_subs is True:
                 event_config["created"] = event_config["updated"] = event_config["deleted"] = True

        model_type = self.type_generator.generate_object_type(model)
        filter_input = self.nested_filter_generator.generate_where_input(model)
        subscriptions: dict[str, graphene.Field] = {}
        for event, enabled in event_config.items():
            if not enabled: continue
            subscription_class, arguments = self._build_subscription_class(model, model_type, event, filter_input)
            field_name = f"{model.__name__.lower()}_{event}"
            
            # The field resolver logic:
            # 1. If is_subscription=True context, call 'subscribe' to get groups.
            # 2. If is_publication=True context, call 'publish' to get data.
            def create_field_resolver(s_class):
                def resolver(root, info, **kwargs):
                    context = info.context
                    if getattr(context, "is_subscription", False):
                        return s_class.subscribe(root, info, **kwargs)
                    if getattr(context, "is_publication", False):
                        return s_class.publish(root, info, **kwargs)
                    return None
                return resolver

            subscriptions[field_name] = graphene.Field(
                subscription_class,
                args=arguments,
                resolver=create_field_resolver(subscription_class)
            )
            register_subscription(self.schema_name, model._meta.label_lower, event, subscription_class)
        return subscriptions

    def generate_all_subscriptions(self, models_list: Iterable[type[models.Model]]) -> dict[str, graphene.Field]:
        subscriptions: dict[str, graphene.Field] = {}
        if not self.settings.enable_subscriptions: return subscriptions
        for model in models_list:
            if not self._model_is_allowed(model): continue
            subscriptions.update(self.generate_model_subscriptions(model))
        return subscriptions
