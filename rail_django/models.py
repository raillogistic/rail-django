"""
Model registry for rail_django extensions.

This module imports reporting models so Django auto-discovery registers them and
the GraphQL auto schema can expose CRUD and method-based mutations.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from django.core.exceptions import ValidationError
from django.db import models as django_models

from rail_django.config.defaults import LIBRARY_DEFAULTS
from rail_django.extensions.audit import AuditEventModel
from rail_django.extensions.reporting import (
    ReportingDataset,
    ReportingExportJob,
    ReportingReport,
    ReportingReportBlock,
    ReportingVisualization,
)
from rail_django.extensions.tasks import TaskExecution
from rail_django.extensions.filters.models import SavedFilter
from rail_django.validation.schema_validator import SchemaValidator


def _default_section(section: str) -> dict[str, Any]:
    return copy.deepcopy(LIBRARY_DEFAULTS.get(section, {}))


def _default_schema_settings() -> dict[str, Any]:
    return _default_section("schema_settings")


def _default_type_generation_settings() -> dict[str, Any]:
    return _default_section("type_generation_settings")


def _default_query_settings() -> dict[str, Any]:
    return _default_section("query_settings")


def _default_mutation_settings() -> dict[str, Any]:
    return _default_section("mutation_settings")


def _default_subscription_settings() -> dict[str, Any]:
    return _default_section("subscription_settings")


def _default_performance_settings() -> dict[str, Any]:
    return _default_section("performance_settings")


def _default_persisted_query_settings() -> dict[str, Any]:
    return _default_section("persisted_query_settings")


def _default_security_settings() -> dict[str, Any]:
    return _default_section("security_settings")


def _default_plugin_settings() -> dict[str, Any]:
    return _default_section("plugin_settings")


def _default_middleware_settings() -> dict[str, Any]:
    return _default_section("middleware_settings")


def _default_error_handling() -> dict[str, Any]:
    return _default_section("error_handling")


def _default_custom_scalars() -> dict[str, Any]:
    return _default_section("custom_scalars")


def _default_monitoring_settings() -> dict[str, Any]:
    return _default_section("monitoring_settings")


def _default_schema_registry_settings() -> dict[str, Any]:
    return _default_section("schema_registry")


def _ensure_dict(value: Any, default_value: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return copy.deepcopy(default_value)


def _ensure_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


class SchemaRegistryModel(django_models.Model):
    """Persisted schema registry entry used for auto-discovery."""

    name = django_models.SlugField(max_length=50, unique=True)
    description = django_models.TextField(blank=True)
    version = django_models.CharField(max_length=50, default="1.0.0")
    enabled = django_models.BooleanField(default=True)
    auto_discover = django_models.BooleanField(default=True)
    apps = django_models.JSONField(default=list, blank=True)
    models = django_models.JSONField(default=list, blank=True)
    exclude_models = django_models.JSONField(default=list, blank=True)

    schema_settings = django_models.JSONField(default=_default_schema_settings)
    type_generation_settings = django_models.JSONField(default=_default_type_generation_settings)
    query_settings = django_models.JSONField(default=_default_query_settings)
    mutation_settings = django_models.JSONField(default=_default_mutation_settings)
    subscription_settings = django_models.JSONField(default=_default_subscription_settings)
    performance_settings = django_models.JSONField(default=_default_performance_settings)
    persisted_query_settings = django_models.JSONField(
        default=_default_persisted_query_settings
    )
    security_settings = django_models.JSONField(default=_default_security_settings)
    plugin_settings = django_models.JSONField(default=_default_plugin_settings)
    middleware_settings = django_models.JSONField(default=_default_middleware_settings)
    error_handling = django_models.JSONField(default=_default_error_handling)
    custom_scalars = django_models.JSONField(default=_default_custom_scalars)
    monitoring_settings = django_models.JSONField(default=_default_monitoring_settings)
    schema_registry_settings = django_models.JSONField(default=_default_schema_registry_settings)

    created_at = django_models.DateTimeField(auto_now_add=True)
    updated_at = django_models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rail_django_schema_registry"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.version})"

    def clean(self) -> None:
        name = (self.name or "").strip()
        if not name:
            raise ValidationError({"name": "Schema name is required."})

        if not SchemaValidator.SCHEMA_NAME_PATTERN.match(name):
            raise ValidationError(
                {
                    "name": (
                        "Schema name must start with a letter and contain only "
                        "letters, numbers, underscores, and hyphens."
                    )
                }
            )

        if len(name) > SchemaValidator.MAX_SCHEMA_NAME_LENGTH:
            raise ValidationError(
                {
                    "name": (
                        f"Schema name exceeds {SchemaValidator.MAX_SCHEMA_NAME_LENGTH} characters."
                    )
                }
            )

        if name.lower() in SchemaValidator.RESERVED_NAMES:
            raise ValidationError(
                {"name": f"Schema name '{name}' is reserved and cannot be used."}
            )

    def get_settings_payload(self) -> dict[str, Any]:
        """Return the combined settings payload for registry registration."""
        return {
            "schema_settings": _ensure_dict(
                self.schema_settings, _default_schema_settings()
            ),
            "type_generation_settings": _ensure_dict(
                self.type_generation_settings, _default_type_generation_settings()
            ),
            "query_settings": _ensure_dict(
                self.query_settings, _default_query_settings()
            ),
            "mutation_settings": _ensure_dict(
                self.mutation_settings, _default_mutation_settings()
            ),
            "subscription_settings": _ensure_dict(
                self.subscription_settings, _default_subscription_settings()
            ),
            "performance_settings": _ensure_dict(
                self.performance_settings, _default_performance_settings()
            ),
            "persisted_query_settings": _ensure_dict(
                self.persisted_query_settings, _default_persisted_query_settings()
            ),
            "security_settings": _ensure_dict(
                self.security_settings, _default_security_settings()
            ),
            "plugin_settings": _ensure_dict(
                self.plugin_settings, _default_plugin_settings()
            ),
            "middleware_settings": _ensure_dict(
                self.middleware_settings, _default_middleware_settings()
            ),
            "error_handling": _ensure_dict(
                self.error_handling, _default_error_handling()
            ),
            "custom_scalars": _ensure_dict(
                self.custom_scalars, _default_custom_scalars()
            ),
            "monitoring_settings": _ensure_dict(
                self.monitoring_settings, _default_monitoring_settings()
            ),
            "schema_registry": _ensure_dict(
                self.schema_registry_settings, _default_schema_registry_settings()
            ),
        }

    def to_registry_kwargs(self) -> dict[str, Any]:
        """Build kwargs for schema_registry.register_schema."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "apps": _ensure_list(self.apps),
            "models": _ensure_list(self.models),
            "exclude_models": _ensure_list(self.exclude_models),
            "settings": self.get_settings_payload(),
            "auto_discover": bool(self.auto_discover),
            "enabled": bool(self.enabled),
        }


class SchemaSnapshotModel(django_models.Model):
    """Stored snapshot of a schema for diff/export history."""

    schema_name = django_models.SlugField(max_length=50, db_index=True)
    version = django_models.CharField(max_length=50)
    schema_hash = django_models.CharField(max_length=64, db_index=True)
    schema_sdl = django_models.TextField(blank=True)
    schema_json = django_models.JSONField(default=dict)
    created_at = django_models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rail_django_schema_snapshot"
        ordering = ["-created_at"]
        unique_together = ("schema_name", "version")

    def __str__(self) -> str:
        return f"{self.schema_name} ({self.version})"


class MetadataDeployVersionModel(django_models.Model):
    """Deployment-level metadata version for cache invalidation."""

    key = django_models.SlugField(max_length=50, unique=True, default="default")
    version = django_models.CharField(max_length=64, default="init")
    updated_at = django_models.DateTimeField(auto_now=True)
    created_at = django_models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rail_django_metadata_deploy_version"
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key} ({self.version})"


__all__ = [
    "AuditEventModel",
    "ReportingDataset",
    "ReportingVisualization",
    "ReportingReport",
    "ReportingReportBlock",
    "ReportingExportJob",
    "TaskExecution",
    "SchemaRegistryModel",
    "SchemaSnapshotModel",
    "MetadataDeployVersionModel",
    "SavedFilter",
]
