"""
Admin registrations for rail_django registry models.
"""

from __future__ import annotations

import json
import logging

from django.apps import apps as django_apps
from django import forms
from django.contrib import admin, messages
from django.forms.widgets import Textarea
from django.http import JsonResponse
from django.urls import path

from rail_django.core.registry import schema_registry
from rail_django.defaults import LIBRARY_DEFAULTS
from rail_django.models import SchemaRegistryModel

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

REGISTRY_UI_FIELDS = SCHEMA_JSON_FIELDS

HIDDEN_APP_LABELS = {
    "admin",
    "contenttypes",
    "sessions",
    "messages",
    "staticfiles",
    "rail_django",
    "graphene_django",
    "root",
}

SETTINGS_SECTIONS = (
    ("schema_settings", "Schema Settings", "schema_settings"),
    ("type_generation_settings", "Type Generation Settings", "type_generation_settings"),
    ("query_settings", "Query Settings", "query_settings"),
    ("mutation_settings", "Mutation Settings", "mutation_settings"),
    ("performance_settings", "Performance Settings", "performance_settings"),
    ("security_settings", "Security Settings", "security_settings"),
    ("middleware_settings", "Middleware Settings", "middleware_settings"),
    ("error_handling", "Error Handling", "error_handling"),
    ("custom_scalars", "Custom Scalars", "custom_scalars"),
    ("monitoring_settings", "Monitoring Settings", "monitoring_settings"),
    ("schema_registry_settings", "Schema Registry Settings", "schema_registry"),
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
        for field_name in REGISTRY_UI_FIELDS:
            if field_name in self.fields:
                widget = self.fields[field_name].widget
                classes = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{classes} rail-registry-json".strip()
                widget.attrs["data-rail-field"] = field_name


@admin.register(SchemaRegistryModel)
class SchemaRegistryModelAdmin(admin.ModelAdmin):
    form = SchemaRegistryModelForm
    change_form_template = "admin/rail_django/schemaregistrymodel/change_form.html"
    add_form_template = "admin/rail_django/schemaregistrymodel/change_form.html"
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

    class Media:
        css = {"all": ("rail_django/admin/schema_registry_editor.css",)}
        js = ("rail_django/admin/schema_registry_editor.js",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "ui-data/",
                self.admin_site.admin_view(self.ui_data_view),
                name="rail_django_schemaregistrymodel_ui_data",
            ),
        ]
        return custom_urls + urls

    def ui_data_view(self, request):
        return JsonResponse(self._build_ui_payload())

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

    def _build_ui_payload(self):
        return {
            "apps": self._build_app_payload(),
            "settings": self._build_settings_payload(),
        }

    def _build_app_payload(self):
        app_payload = []
        for app_config in django_apps.get_app_configs():
            if app_config.label in HIDDEN_APP_LABELS or (
                app_config.name.startswith("django.contrib.")
                and app_config.label != "auth"
            ):
                continue
            models_payload = []
            for model in app_config.get_models():
                models_payload.append(
                    {
                        "label": f"{app_config.label}.{model.__name__}",
                        "app_label": app_config.label,
                        "model_name": model.__name__,
                        "model_key": model._meta.model_name,
                        "verbose_name": str(model._meta.verbose_name),
                        "verbose_name_plural": str(model._meta.verbose_name_plural),
                    }
                )
            models_payload.sort(key=lambda item: item["label"].lower())
            app_payload.append(
                {
                    "label": app_config.label,
                    "name": app_config.name,
                    "verbose_name": str(app_config.verbose_name),
                    "models": models_payload,
                }
            )
        app_payload.sort(key=lambda item: item["label"].lower())
        return app_payload

    def _build_settings_payload(self):
        sections = {}
        order = []
        for field_name, label, defaults_key in SETTINGS_SECTIONS:
            defaults = LIBRARY_DEFAULTS.get(defaults_key, {})
            sections[field_name] = {
                "label": label,
                "options": self._build_setting_options(defaults),
            }
            order.append(field_name)
        return {"order": order, "sections": sections}

    def _build_setting_options(self, defaults):
        options = []
        for key, value in defaults.items():
            options.append(
                {
                    "key": key,
                    "default": value,
                    **self._infer_setting_type(value),
                }
            )
        options.sort(key=lambda item: item["key"])
        return options

    @staticmethod
    def _infer_setting_type(value):
        if isinstance(value, bool):
            return {"type": "boolean", "nullable": False}
        if isinstance(value, list):
            return {"type": "string_list", "nullable": False}
        if value is None:
            return {"type": "string_list", "nullable": True}
        return {"type": "json", "nullable": False}
