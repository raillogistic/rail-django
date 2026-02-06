"""Derive table config from Django model metadata."""

from __future__ import annotations


def extract_table_config(model_cls) -> dict:
    columns = []
    for field in model_cls._meta.fields:
        columns.append(
            {
                "id": field.name,
                "accessor": field.name,
                "label": str(getattr(field, "verbose_name", field.name)),
                "type": field.get_internal_type(),
                "width": None,
            }
        )

    return {
        "columns": columns,
        "defaultSort": [{"field": "id", "direction": "DESC"}],
        "quickSearchFields": [
            f.name
            for f in model_cls._meta.fields
            if f.get_internal_type() in {"CharField", "TextField"}
        ],
        "pagination": {"defaultPageSize": 25},
    }
