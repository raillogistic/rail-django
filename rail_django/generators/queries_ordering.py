"""
Ordering helpers for query generation.
"""

from typing import Any, List, Optional, Tuple, Type

from django.db import models
from django.db.models import Count

from .introspector import ModelIntrospector


DEFAULT_ORDERING_FALLBACK = ["-id"]


def get_default_ordering(ordering_config) -> List[str]:
    if ordering_config and getattr(ordering_config, "default", None):
        return list(ordering_config.default)
    return list(DEFAULT_ORDERING_FALLBACK)


def apply_count_annotations_for_ordering(
    queryset: models.QuerySet,
    model: type,
    order_by: List[str],
) -> Tuple[models.QuerySet, List[str]]:
    """
    Annotate queryset for any order_by fields that request <relation>_count or <relation>__count.
    Supports forward ManyToMany and reverse relations using accessor names.
    Returns updated queryset and a possibly transformed order_by list.
    """
    if not order_by:
        return queryset, order_by

    new_order_by: List[str] = []
    annotated_aliases: set = set()

    for spec in order_by:
        desc = spec.startswith("-")
        field = spec[1:] if desc else spec

        base = None
        alias = None

        if field.endswith("_count"):
            base = field[: -len("_count")]
            alias = f"{base}_count"
        elif field.endswith("__count"):
            base = field[: -len("__count")]
            alias = field

        if base:
            # Determine if base is a ManyToMany relation to apply distinct
            is_m2m = False
            try:
                # Check forward fields
                for f in model._meta.get_fields():
                    if getattr(f, "name", None) == base:
                        try:
                            from django.db.models.fields.related import (
                                ManyToManyField,
                            )
                            from django.db.models.fields.reverse_related import (
                                ManyToManyRel,
                            )

                            is_m2m = isinstance(f, ManyToManyField) or isinstance(
                                f, ManyToManyRel
                            )
                        except Exception:
                            pass
                        break
                else:
                    # Check reverse relations by accessor name
                    if hasattr(model._meta, "related_objects"):
                        from django.db.models.fields.reverse_related import (
                            ManyToManyRel,
                        )

                        for rel in model._meta.related_objects:
                            if rel.get_accessor_name() == base:
                                is_m2m = isinstance(rel, ManyToManyRel)
                                break
            except Exception:
                # If introspection fails, default to non-distinct
                is_m2m = False

            if alias and alias not in annotated_aliases:
                try:
                    queryset = queryset.annotate(
                        **{alias: Count(base, distinct=is_m2m)}
                    )
                    annotated_aliases.add(alias)
                except Exception:
                    try:
                        queryset = queryset.annotate(**{alias: Count(base)})
                        annotated_aliases.add(alias)
                    except Exception:
                        # If annotation fails, fall back to original spec
                        alias = None

            if alias:
                new_order_by.append(f"-{alias}" if desc else alias)
            else:
                new_order_by.append(spec)
        else:
            new_order_by.append(spec)

    return queryset, new_order_by


def normalize_ordering_specs(
    order_by: Optional[List[str]],
    ordering_config,
    schema_name: Optional[str] = None,
) -> List[str]:
    """
    Apply default ordering and validate specs against GraphQLMeta configuration.
    """
    normalized = [spec for spec in (order_by or []) if spec]
    if not normalized:
        normalized = get_default_ordering(ordering_config)

    allowed = getattr(ordering_config, "allowed", None) or []
    if allowed and normalized:
        invalid = [spec for spec in normalized if spec.lstrip("-") not in allowed]
        if invalid:
            raise ValueError(
                f"Unsupported ordering fields for {schema_name or 'default'}: {', '.join(invalid)}"
            )

    return normalized


def split_order_specs(
    model: Type[models.Model], order_by: List[str]
) -> Tuple[List[str], List[str]]:
    """Split order_by specs into DB fields and property-based fields."""
    if not order_by:
        return [], []
    try:
        introspector = ModelIntrospector(model)
        prop_names = set(introspector.properties.keys())
    except Exception:
        prop_names = set()
    db_specs: List[str] = []
    prop_specs: List[str] = []
    for spec in order_by:
        name = spec[1:] if spec.startswith("-") else spec
        if name in prop_names:
            prop_specs.append(spec)
        else:
            db_specs.append(spec)
    return db_specs, prop_specs


def safe_prop_value(obj: Any, prop_name: str):
    """Return a comparable key for property sorting, nulls last."""
    try:
        val = getattr(obj, prop_name)
    except Exception:
        val = None
    if val is None:
        return (1, None)
    # If value is not directly comparable, fall back to string representation
    try:
        _ = val < val  # type check to ensure comparable
        return (0, val)
    except Exception:
        return (0, str(val))


def apply_property_ordering(
    items: List[Any], prop_specs: List[str]
) -> List[Any]:
    """Apply stable multi-key sort on a Python list based on property specs."""
    if not prop_specs:
        return items
    # Stable sort: apply from last to first
    for spec in reversed(prop_specs):
        desc = spec.startswith("-")
        name = spec[1:] if desc else spec
        try:
            items.sort(key=lambda o: safe_prop_value(o, name), reverse=desc)
        except Exception:
            # If sorting fails, skip this spec
            continue
    return items
