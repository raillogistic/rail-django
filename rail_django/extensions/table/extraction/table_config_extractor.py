"""Derive table config from Django model metadata."""

from __future__ import annotations


def extract_table_config(
    model_cls,
    *,
    visible_fields: list[str] | None = None,
    editable_fields: set[str] | None = None,
) -> dict:
    allowed = set(visible_fields or [])
    editable = set(editable_fields or set())
    columns = []
    for field in model_cls._meta.fields:
        if allowed and field.name not in allowed:
            continue
        columns.append(
            {
                "id": field.name,
                "accessor": field.name,
                "label": str(getattr(field, "verbose_name", field.name)),
                "type": field.get_internal_type(),
                "width": None,
                "editable": field.name in editable,
            }
        )

    default_sort_field = "id" if any(col["id"] == "id" for col in columns) else (
        columns[0]["id"] if columns else "id"
    )
    return {
        "columns": columns,
        "defaultSort": [{"field": default_sort_field, "direction": "DESC"}],
        "quickSearchFields": [
            f.name
            for f in model_cls._meta.fields
            if (not allowed or f.name in allowed)
            and f.get_internal_type() in {"CharField", "TextField"}
        ],
        "pagination": {"defaultPageSize": 25},
    }
