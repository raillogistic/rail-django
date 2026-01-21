"""
Internal utility functions for subscription generation.
"""

import copy
import hashlib
import re
from datetime import date, datetime
from typing import Any, Iterable, Optional

import graphene
from django.contrib.auth.models import AnonymousUser
from django.db import models
from django.utils import timezone

from ...security.field_permissions import mask_sensitive_fields

_GROUP_NAME_SAFE_RE = re.compile(r"[^0-9A-Za-z_.-]")


def _get_subscription_base() -> type:
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


def _get_context_user(info: graphene.ResolveInfo) -> Any:
    context = getattr(info, "context", None)
    if context is None:
        return None
    if isinstance(context, dict):
        user = context.get("user")
        if user is not None: return user
        scope = context.get("scope")
        if isinstance(scope, dict): return scope.get("user")
        return None
    user = getattr(context, "user", None)
    if user is not None: return user
    scope = getattr(context, "scope", None)
    if isinstance(scope, dict): return scope.get("user")
    return None


def _coerce_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _apply_field_masks(
    instance: models.Model, info: graphene.ResolveInfo, model: type[models.Model]
) -> models.Model:
    masked_instance = copy.copy(instance)
    context_user = _get_context_user(info)
    if context_user is None:
        context_user = AnonymousUser()
    if getattr(context_user, "is_superuser", False):
        return masked_instance

    field_defs = list(masked_instance._meta.concrete_fields)
    snapshot: dict[str, Any] = {}
    for field in field_defs:
        if field.is_relation and (field.many_to_one or field.one_to_one):
            val = getattr(masked_instance, field.attname, None)
        else:
            val = getattr(masked_instance, field.name, None)
        snapshot[field.name] = val

    masked = mask_sensitive_fields(snapshot, context_user, model, instance=masked_instance)
    for field in field_defs:
        name = field.name
        attname = getattr(field, "attname", name)
        if name in masked:
            masked_instance.__dict__[attname] = masked[name]
        else:
            masked_instance.__dict__[attname] = None
    return masked_instance


def _build_instance_from_payload(
    model: type[models.Model], payload: Any
) -> Optional[models.Model]:
    if not isinstance(payload, dict):
        return None
    instance = payload.get("instance")
    if isinstance(instance, model):
        return instance
    snapshot = payload.get("snapshot") or payload.get("instance_data") or payload.get("data")
    if isinstance(snapshot, dict):
        field_names = {field.attname for field in model._meta.concrete_fields}
        instance = model()
        for key, value in snapshot.items():
            if key == "pk": key = model._meta.pk.attname
            if key in field_names: setattr(instance, key, value)
        if getattr(instance, "pk", None) is not None:
            instance._state.adding = False
        return instance
    pk = payload.get("pk") or payload.get("id") or payload.get("instance_id")
    if pk is not None:
        instance = model()
        setattr(instance, model._meta.pk.attname, pk)
        instance._state.adding = False
        return instance
    return None
