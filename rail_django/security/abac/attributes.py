"""
Attribute providers for ABAC.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from django.db import models

from .types import AttributeSet

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class BaseAttributeProvider(ABC):
    """Base provider class."""

    @abstractmethod
    def collect(self, **kwargs) -> AttributeSet:
        raise NotImplementedError


class SubjectAttributeProvider(BaseAttributeProvider):
    """Collect attributes for the subject (user)."""

    def collect(self, user: "AbstractUser" = None, **kwargs) -> AttributeSet:
        if user is None or not getattr(user, "is_authenticated", False):
            return AttributeSet(static_attributes={"authenticated": False})

        attrs = {
            "authenticated": True,
            "user_id": getattr(user, "pk", None),
            "username": getattr(user, "username", ""),
            "email": getattr(user, "email", ""),
            "is_staff": bool(getattr(user, "is_staff", False)),
            "is_superuser": bool(getattr(user, "is_superuser", False)),
            "is_active": bool(getattr(user, "is_active", False)),
            "date_joined": getattr(user, "date_joined", None),
            "last_login": getattr(user, "last_login", None),
            "roles": [],
        }

        try:
            attrs["roles"] = list(user.groups.values_list("name", flat=True))
        except Exception:
            attrs["roles"] = []

        profile = getattr(user, "profile", None)
        if profile is not None:
            for attr in ("department", "organization", "team", "location", "level"):
                if hasattr(profile, attr):
                    attrs[attr] = getattr(profile, attr)

        return AttributeSet(
            static_attributes=attrs,
            dynamic_resolvers={
                "permissions": lambda: set(user.get_all_permissions()),
            },
        )


class ResourceAttributeProvider(BaseAttributeProvider):
    """Collect attributes for a resource instance/model."""

    def collect(
        self,
        instance: Optional[models.Model] = None,
        model_class: Optional[type[models.Model]] = None,
        **kwargs,
    ) -> AttributeSet:
        model = model_class or (instance.__class__ if instance is not None else None)
        if model is None:
            return AttributeSet()

        meta = getattr(model, "_meta", None)
        if meta is not None:
            attrs: dict[str, object] = {
                "model_name": meta.model_name,
                "app_label": meta.app_label,
                "model_label": meta.label_lower,
            }
        else:
            attrs = {
                "model_name": getattr(model, "__name__", "").lower(),
                "app_label": "",
                "model_label": getattr(model, "__name__", "").lower(),
            }

        if instance is not None:
            if meta is not None:
                for field in meta.get_fields():
                    attname = getattr(field, "attname", None)
                    if not attname:
                        continue
                    if not hasattr(instance, attname):
                        continue
                    attrs[field.name] = getattr(instance, attname)
            else:
                try:
                    attrs.update(vars(instance))
                except Exception:
                    pass

            for owner_attr in ("owner", "created_by", "user"):
                owner_id_attr = f"{owner_attr}_id"
                if hasattr(instance, owner_id_attr):
                    attrs["owner_id"] = getattr(instance, owner_id_attr)
                    break

        graphql_meta = getattr(model, "GraphQLMeta", None) or getattr(
            model, "GraphqlMeta", None
        )
        if graphql_meta is not None:
            attrs["classification"] = getattr(graphql_meta, "classification", None)
            attrs["sensitivity"] = getattr(graphql_meta, "sensitivity", None)

        return AttributeSet(static_attributes=attrs)


class EnvironmentAttributeProvider(BaseAttributeProvider):
    """Collect environment attributes from request/runtime."""

    def collect(self, request: "HttpRequest" = None, **kwargs) -> AttributeSet:
        now = datetime.now(timezone.utc)
        attrs: dict[str, object] = {
            "current_time": now,
            "current_date": now.date(),
            "day_of_week": now.strftime("%A").lower(),
            "hour": now.hour,
            "is_business_hours": 8 <= now.hour <= 18,
        }

        if request is not None:
            attrs["client_ip"] = self._get_client_ip(request)
            meta = getattr(request, "META", {}) or {}
            if not isinstance(meta, dict):
                meta = {}
            attrs["user_agent"] = meta.get("HTTP_USER_AGENT", "")
            is_secure = getattr(request, "is_secure", None)
            attrs["is_secure"] = bool(is_secure() if callable(is_secure) else is_secure)
            attrs["request_method"] = getattr(request, "method", "")
            attrs["request_path"] = getattr(request, "path", "")

        return AttributeSet(static_attributes=attrs)

    @staticmethod
    def _get_client_ip(request: "HttpRequest") -> Optional[str]:
        meta = getattr(request, "META", {}) or {}
        if not isinstance(meta, dict):
            return None
        xff = meta.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return meta.get("REMOTE_ADDR")


class ActionAttributeProvider(BaseAttributeProvider):
    """Collect action attributes for the evaluated operation."""

    def collect(
        self,
        operation: Optional[str] = None,
        permission: Optional[str] = None,
        info: object = None,
        **kwargs,
    ) -> AttributeSet:
        attrs: dict[str, object] = {
            "type": operation or "",
            "permission": permission or "",
            "operation_name": "",
        }

        if info is not None:
            try:
                op = getattr(info, "operation", None)
                if op is not None:
                    op_type = getattr(getattr(op, "operation", None), "value", None)
                    if op_type:
                        attrs["type"] = op_type
                    op_name = getattr(op, "name", None)
                    if hasattr(op_name, "value"):
                        attrs["operation_name"] = op_name.value or ""
                    elif isinstance(op_name, str):
                        attrs["operation_name"] = op_name
            except Exception:
                logger.debug("Could not extract action attributes from GraphQL info")

        return AttributeSet(static_attributes=attrs)
