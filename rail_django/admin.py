"""
Admin registrations for rail_django registry models.
"""

from __future__ import annotations

import json
import logging

from django import forms
from django.contrib import admin, messages
from django.forms.widgets import Textarea

from rail_django.core.registry import schema_registry
from rail_django.core.schema_versioning import schema_version_manager
from rail_django.models import SchemaRegistryModel, SchemaVersionModel

logger = logging.getLogger(__name__)


class PrettyJSONWidget(Textarea):
    """Pretty-print JSON in admin textareas."""

    def __init__(self, *args, **kwargs):
        attrs = {"rows": 8, "cols": 90}
        attrs.update(kwargs.pop("attrs", {}))
        super().__init__(attrs=attrs)

    def format_value(self, value):
        if value in (None, ""):
            return ""
        try:
            return json.dumps(value, indent=2, sort_keys=True)
        except (TypeError, ValueError):
            return super().format_value(value)


SCHEMA_JSON_FIELDS = (
    "apps",
    "models",
    "exclude_models",
    "schema_settings",
    "type_generation_settings",
    "query_settings",
    "mutation_settings",
    "performance_settings",
    "security_settings",
    "middleware_settings",
    "error_handling",
    "custom_scalars",
    "monitoring_settings",
    "schema_registry_settings",
)


class SchemaRegistryModelForm(forms.ModelForm):
    class Meta:
        model = SchemaRegistryModel
        fields = "__all__"
        widgets = {field: PrettyJSONWidget() for field in SCHEMA_JSON_FIELDS}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            for field_name in SCHEMA_JSON_FIELDS:
                if field_name not in self.initial:
                    self.initial[field_name] = getattr(self.instance, field_name)


@admin.register(SchemaRegistryModel)
class SchemaRegistryModelAdmin(admin.ModelAdmin):
    form = SchemaRegistryModelForm
    list_display = ("name", "version", "enabled", "auto_discover", "updated_at")
    list_filter = ("enabled", "auto_discover")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Core", {"fields": ("name", "description", "version", "enabled", "auto_discover")}),
        ("Model Scope", {"fields": ("apps", "models", "exclude_models")}),
        ("Schema Settings", {"fields": ("schema_settings",)}),
        ("Type Generation Settings", {"fields": ("type_generation_settings",), "classes": ("collapse",)}),
        ("Query Settings", {"fields": ("query_settings",), "classes": ("collapse",)}),
        ("Mutation Settings", {"fields": ("mutation_settings",), "classes": ("collapse",)}),
        ("Performance Settings", {"fields": ("performance_settings",), "classes": ("collapse",)}),
        ("Security Settings", {"fields": ("security_settings",), "classes": ("collapse",)}),
        ("Middleware Settings", {"fields": ("middleware_settings",), "classes": ("collapse",)}),
        ("Error Handling", {"fields": ("error_handling",), "classes": ("collapse",)}),
        ("Custom Scalars", {"fields": ("custom_scalars",), "classes": ("collapse",)}),
        ("Monitoring Settings", {"fields": ("monitoring_settings",), "classes": ("collapse",)}),
        ("Registry Settings", {"fields": ("schema_registry_settings",), "classes": ("collapse",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._sync_registry(request, obj)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        schema_registry.unregister_schema(obj.name)

    def delete_queryset(self, request, queryset):
        names = [entry.name for entry in queryset]
        super().delete_queryset(request, queryset)
        for name in names:
            schema_registry.unregister_schema(name)

    def _sync_registry(self, request, obj: SchemaRegistryModel) -> None:
        try:
            schema_info = schema_registry.register_schema(**obj.to_registry_kwargs())
            if schema_info:
                schema_info.created_at = (
                    obj.created_at.isoformat() if obj.created_at else None
                )
                schema_info.updated_at = (
                    obj.updated_at.isoformat() if obj.updated_at else None
                )
        except Exception as exc:
            logger.warning("Schema registry sync failed for %s: %s", obj.name, exc)
            messages.warning(
                request,
                f"Schema registry sync failed for '{obj.name}': {exc}",
            )


@admin.register(SchemaVersionModel)
class SchemaVersionModelAdmin(admin.ModelAdmin):
    list_display = ("version", "is_active", "created_at", "created_by", "schema_hash_short")
    list_filter = ("is_active", "created_at")
    search_fields = ("version", "description", "created_by")
    readonly_fields = ("schema_hash", "created_at")
    actions = ("activate_selected_version",)

    @admin.display(description="Schema hash")
    def schema_hash_short(self, obj: SchemaVersionModel) -> str:
        if not obj.schema_hash:
            return ""
        return f"{obj.schema_hash[:12]}..."

    def activate_selected_version(self, request, queryset):
        if queryset.count() != 1:
            messages.warning(request, "Select exactly one schema version to activate.")
            return

        version = queryset.first().version
        if schema_version_manager.activate_version(version):
            messages.success(request, f"Activated schema version {version}.")
        else:
            messages.error(request, f"Failed to activate schema version {version}.")
