"""
Configuration Builders for GraphQL Meta

This module provides functions for building configuration dataclass instances
from raw meta class declarations. These functions handle legacy format
fallbacks and normalization.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import (
    AccessControlConfig,
    ClassificationConfig,
    FieldExposureConfig,
    FilteringConfig,
    OrderingConfig,
    PipelineConfig,
    ResolverConfig,
)
from .coercion import (
    coerce_field_guard,
    coerce_filter_field_config,
    coerce_operation_guard,
    coerce_role_config,
)

logger = logging.getLogger(__name__)


def build_filtering_config(meta_config: Any) -> FilteringConfig:
    """
    Construct filtering configuration with legacy fallbacks.

    Args:
        meta_config: The model's GraphQLMeta configuration class

    Returns:
        Normalized FilteringConfig instance
    """
    if not meta_config:
        return FilteringConfig()

    raw = getattr(meta_config, "filtering", None)
    if isinstance(raw, FilteringConfig):
        config = FilteringConfig(
            quick=list(raw.quick),
            quick_lookup=raw.quick_lookup,
            auto_detect_quick=raw.auto_detect_quick,
            fields={
                name: coerce_filter_field_config(value)
                for name, value in raw.fields.items()
            },
            custom=dict(raw.custom),
            presets=dict(raw.presets),
        )
    elif isinstance(raw, dict):
        config = FilteringConfig(
            quick=list(raw.get("quick", [])),
            quick_lookup=raw.get("quick_lookup", "icontains"),
            auto_detect_quick=raw.get("auto_detect_quick", True),
            fields={
                name: coerce_filter_field_config(value)
                for name, value in raw.get("fields", {}).items()
            },
            custom=dict(raw.get("custom", {})),
            presets=dict(raw.get("presets", {})),
        )
    else:
        config = FilteringConfig()

    # Apply legacy fallbacks
    if not config.presets:
        legacy_presets = getattr(meta_config, "filter_presets", {})
        if isinstance(legacy_presets, dict):
            config.presets = dict(legacy_presets)

    if not config.custom:
        legacy_custom = getattr(meta_config, "custom_filters", {})
        if isinstance(legacy_custom, dict):
            config.custom = dict(legacy_custom)

    if not config.quick:
        legacy_quick = getattr(meta_config, "quick_filter_fields", None)
        if legacy_quick:
            config.quick = list(legacy_quick)

    legacy_filters = getattr(meta_config, "filters", {})
    if isinstance(legacy_filters, dict):
        for name, value in legacy_filters.items():
            config.fields.setdefault(name, coerce_filter_field_config(value))

    legacy_filter_fields = getattr(meta_config, "filter_fields", {})
    if isinstance(legacy_filter_fields, dict):
        for name, value in legacy_filter_fields.items():
            if name == "quick" and not config.quick:
                if isinstance(value, (list, tuple)):
                    config.quick = list(value)
                elif isinstance(value, str):
                    config.quick = [value]
                continue
            config.fields.setdefault(name, coerce_filter_field_config(value))

    return config


def build_field_config(meta_config: Any) -> FieldExposureConfig:
    """
    Construct field exposure configuration.

    Args:
        meta_config: The model's GraphQLMeta configuration class

    Returns:
        Normalized FieldExposureConfig instance
    """
    if not meta_config:
        return FieldExposureConfig()

    raw = getattr(meta_config, "fields", None)
    if isinstance(raw, FieldExposureConfig):
        return FieldExposureConfig(
            include=list(raw.include) if raw.include else None,
            exclude=list(raw.exclude),
            read_only=list(raw.read_only),
            write_only=list(raw.write_only),
        )
    if isinstance(raw, dict):
        include = raw.get("include")
        if include is not None:
            include = list(include)
        return FieldExposureConfig(
            include=include,
            exclude=list(raw.get("exclude", [])),
            read_only=list(raw.get("read_only", [])),
            write_only=list(raw.get("write_only", [])),
        )

    include_fields = getattr(meta_config, "include_fields", None)
    if include_fields is not None:
        include_fields = list(include_fields)

    return FieldExposureConfig(
        include=include_fields,
        exclude=list(getattr(meta_config, "exclude_fields", [])),
    )


def build_ordering_config(meta_config: Any, model_class: Any) -> OrderingConfig:
    """
    Construct ordering configuration with Django model fallbacks.

    Args:
        meta_config: The model's GraphQLMeta configuration class
        model_class: The Django model class

    Returns:
        Normalized OrderingConfig instance
    """
    config: OrderingConfig
    if meta_config:
        raw = getattr(meta_config, "ordering", None)
        if isinstance(raw, OrderingConfig):
            config = OrderingConfig(
                allowed=list(raw.allowed),
                default=list(raw.default),
                allow_related=raw.allow_related,
            )
        elif isinstance(raw, dict):
            config = OrderingConfig(
                allowed=list(raw.get("allowed", [])),
                default=list(raw.get("default", [])),
                allow_related=raw.get("allow_related", True),
            )
        elif isinstance(raw, (list, tuple)):
            values = list(raw)
            config = OrderingConfig(allowed=values, default=values)
        else:
            config = OrderingConfig()
    else:
        config = OrderingConfig()

    # Apply fallback defaults from Django model meta
    if not config.default:
        model_meta = getattr(model_class, "_meta", None)
        fallback_default: list[str] = []

        try:
            if model_meta and getattr(model_meta, "ordering", None):
                fallback_default = list(model_meta.ordering)
            elif model_meta and getattr(model_meta, "get_latest_by", None):
                fallback_default = [f"-{model_meta.get_latest_by}"]
            else:
                pk_name = (
                    model_meta.pk.name
                    if model_meta and getattr(model_meta, "pk", None)
                    else "id"
                )
                fallback_default = [f"-{pk_name}"]
        except Exception:
            fallback_default = ["-id"]

        if config.allowed:
            fallback_names = [f.lstrip("-") for f in fallback_default]
            allowed_set = set(config.allowed)
            if not all(name in allowed_set for name in fallback_names):
                safe_default = [f"-{config.allowed[0]}"]
                config.default = safe_default
            else:
                config.default = fallback_default
        else:
            config.default = fallback_default

    return config


def build_resolver_config(meta_config: Any) -> ResolverConfig:
    """
    Construct resolver configuration.

    Args:
        meta_config: The model's GraphQLMeta configuration class

    Returns:
        Normalized ResolverConfig instance
    """
    if not meta_config:
        return ResolverConfig()

    raw = getattr(meta_config, "resolvers", None)
    if isinstance(raw, ResolverConfig):
        return ResolverConfig(
            queries=dict(raw.queries),
            mutations=dict(raw.mutations),
            fields=dict(raw.fields),
        )
    if isinstance(raw, dict):
        return ResolverConfig(
            queries=dict(raw.get("queries", {})),
            mutations=dict(raw.get("mutations", {})),
            fields=dict(raw.get("fields", {})),
        )

    legacy_resolvers = getattr(meta_config, "custom_resolvers", {})
    if isinstance(legacy_resolvers, dict):
        return ResolverConfig(queries=dict(legacy_resolvers))

    return ResolverConfig()


def build_access_control_config(meta_config: Any) -> AccessControlConfig:
    """
    Construct access control configuration.

    Args:
        meta_config: The model's GraphQLMeta configuration class

    Returns:
        Normalized AccessControlConfig instance
    """
    if not meta_config:
        return AccessControlConfig()

    raw = getattr(meta_config, "access", None)
    if isinstance(raw, AccessControlConfig):
        roles = {
            name: coerce_role_config(name, role)
            for name, role in raw.roles.items()
        }
        operations = {
            name: coerce_operation_guard(name, guard)
            for name, guard in raw.operations.items()
        }
        fields = [coerce_field_guard(guard) for guard in raw.fields]
        return AccessControlConfig(
            roles=roles, operations=operations, fields=fields
        )

    if isinstance(raw, dict):
        roles = {}
        for name, cfg in (raw.get("roles") or {}).items():
            roles[name] = coerce_role_config(name, cfg)

        operations = {}
        for name, cfg in (raw.get("operations") or {}).items():
            operations[name] = coerce_operation_guard(name, cfg)

        field_guards = [
            coerce_field_guard(cfg) for cfg in raw.get("fields", [])
        ]
        return AccessControlConfig(
            roles=roles, operations=operations, fields=field_guards
        )

    return AccessControlConfig()


def build_classification_config(meta_config: Any) -> ClassificationConfig:
    """
    Construct classification tags for the model.

    Args:
        meta_config: The model's GraphQLMeta configuration class

    Returns:
        Normalized ClassificationConfig instance
    """
    if not meta_config:
        return ClassificationConfig()

    raw = getattr(meta_config, "classifications", None)
    if raw is None:
        raw = getattr(meta_config, "classification", None)
    if raw is None:
        raw = getattr(meta_config, "data_classification", None)

    if isinstance(raw, ClassificationConfig):
        return ClassificationConfig(
            model=list(raw.model),
            fields={name: list(tags) for name, tags in raw.fields.items()},
        )

    if isinstance(raw, (list, tuple, set)):
        return ClassificationConfig(model=[str(tag) for tag in raw if tag])

    if isinstance(raw, dict):
        model_tags = raw.get("model") or raw.get("tags") or raw.get("model_tags")
        if model_tags is None:
            model_tags = raw.get("classifications") or []
        field_tags = raw.get("fields") or raw.get("field_tags") or {}
        normalized_fields = {}
        for field_name, tags in field_tags.items():
            if not field_name:
                continue
            if isinstance(tags, (list, tuple, set)):
                normalized_fields[field_name] = [str(tag) for tag in tags if tag]
            elif tags:
                normalized_fields[field_name] = [str(tags)]
        return ClassificationConfig(
            model=[str(tag) for tag in model_tags or [] if tag],
            fields=normalized_fields,
        )

    return ClassificationConfig()


def build_pipeline_config(meta_config: Any) -> PipelineConfig:
    """
    Construct mutation pipeline configuration for the model.

    Args:
        meta_config: The model's GraphQLMeta configuration class

    Returns:
        Normalized PipelineConfig instance
    """
    if not meta_config:
        return PipelineConfig()

    raw = getattr(meta_config, "pipeline", None)
    if raw is None:
        return PipelineConfig()

    if isinstance(raw, PipelineConfig):
        return PipelineConfig(
            extra_steps=list(raw.extra_steps),
            skip_steps=list(raw.skip_steps),
            step_order=dict(raw.step_order),
            create_steps=list(raw.create_steps),
            update_steps=list(raw.update_steps),
            delete_steps=list(raw.delete_steps),
        )

    if isinstance(raw, dict):
        return PipelineConfig(
            extra_steps=list(raw.get("extra_steps", [])),
            skip_steps=list(raw.get("skip_steps", [])),
            step_order=dict(raw.get("step_order", {})),
            create_steps=list(raw.get("create_steps", [])),
            update_steps=list(raw.get("update_steps", [])),
            delete_steps=list(raw.get("delete_steps", [])),
        )

    return PipelineConfig()
