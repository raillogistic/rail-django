"""Resolve import template descriptors from excel registry metadata."""

from __future__ import annotations

from django.apps import apps
from django.conf import settings
from django.db import models
from django.urls import NoReverseMatch, reverse

from ...excel.exporter import excel_template_registry
from ..constants import DEFAULT_MAX_FILE_SIZE_BYTES, DEFAULT_MAX_ROWS
from ..types import ImportColumnRule, ImportTemplateDescriptor


def _field_to_column_rule(field: models.Field, required: bool) -> ImportColumnRule:
    choices = [str(value) for value, _label in (field.choices or [])] or None
    format_hint = None
    if getattr(field, "is_relation", False) and getattr(field, "many_to_one", False):
        format_hint = (
            f"Use the related record numeric id (example: {field.name}=1 or {field.name}_id=1)."
        )
    return {
        "name": field.name,
        "required": required,
        "data_type": field.get_internal_type(),
        "format_hint": format_hint,
        "allowed_values": choices,
    }


def _resolve_template_definition(app_label: str, model_name: str):
    for template_path, definition in excel_template_registry.all().items():
        if definition.model is None:
            continue
        if definition.model._meta.app_label != app_label:
            continue
        if definition.model._meta.model_name.lower() != model_name.lower():
            continue
        return template_path, definition
    return None, None


def _resolve_download_url(app_label: str, model_name: str) -> str:
    model_slug = model_name.lower()
    try:
        return (
            reverse(
                "schema_api:model_import_template_download",
                kwargs={"app_label": app_label, "model_name": model_slug},
            )
            + "?format=csv"
        )
    except NoReverseMatch:
        return f"/api/v1/import/templates/{app_label}/{model_slug}/?format=csv"


def _fallback_matching_keys(model: type[models.Model]) -> list[str]:
    unique_fields = [
        field.name
        for field in model._meta.fields
        if getattr(field, "unique", False)
        and not getattr(field, "auto_created", False)
        and field.name != model._meta.pk.name
    ]
    if unique_fields:
        return unique_fields
    return [model._meta.pk.name]


def _column_rules_for_model(model: type[models.Model]) -> tuple[list[ImportColumnRule], list[ImportColumnRule]]:
    required: list[ImportColumnRule] = []
    optional: list[ImportColumnRule] = []
    for field in model._meta.fields:
        if getattr(field, "auto_created", False):
            continue
        if not getattr(field, "editable", True):
            continue
        is_required = (
            not getattr(field, "null", False)
            and not getattr(field, "blank", False)
            and not field.has_default()
            and not getattr(field, "auto_now", False)
            and not getattr(field, "auto_now_add", False)
            and field.name != model._meta.pk.name
        )
        rule = _field_to_column_rule(field, required=is_required)
        if is_required:
            required.append(rule)
        else:
            optional.append(rule)
    return required, optional


def resolve_template_descriptor(app_label: str, model_name: str) -> ImportTemplateDescriptor:
    model = apps.get_model(app_label, model_name)
    template_path, definition = _resolve_template_definition(app_label, model_name)
    required_columns, optional_columns = _column_rules_for_model(model)

    import_config = {}
    if definition is not None:
        import_config = (definition.config or {}).get("import", {}) or {}

    matching_key_fields = import_config.get("matching_key_fields")
    if not isinstance(matching_key_fields, list) or not matching_key_fields:
        matching_key_fields = _fallback_matching_keys(model)
    matching_key_fields = [str(field) for field in matching_key_fields]

    version = str(import_config.get("version") or getattr(settings, "RAIL_IMPORT_TEMPLATE_VERSION", "v1"))
    max_rows = int(import_config.get("max_rows") or DEFAULT_MAX_ROWS)
    max_file_size_bytes = int(
        import_config.get("max_file_size_bytes") or DEFAULT_MAX_FILE_SIZE_BYTES
    )
    accepted_formats = ["CSV", "XLSX"]

    if definition is not None:
        template_id = template_path
    else:
        template_id = f"{app_label}.{model_name}"

    return {
        "template_id": template_id,
        "app_label": app_label,
        "model_name": model_name,
        "version": version,
        "exact_version": version,
        "matching_key_fields": matching_key_fields,
        "required_columns": required_columns,
        "optional_columns": optional_columns,
        "accepted_formats": accepted_formats,
        "max_rows": max_rows,
        "max_file_size_bytes": max_file_size_bytes,
        "download_url": _resolve_download_url(app_label=app_label, model_name=model_name),
    }
