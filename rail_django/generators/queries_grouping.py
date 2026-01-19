"""
Grouping query builders.
"""

import logging
from typing import Any, Optional, Type

import graphene
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models
from django.db.models import Count, ForeignKey, ManyToManyField, OneToOneField
from django.utils.translation import gettext_lazy as _

from ..core.meta import get_model_graphql_meta

# Translatable label for empty/null group values
EMPTY_GROUP_LABEL = _("Not specified")
from ..extensions.optimization import optimize_query

logger = logging.getLogger(__name__)


class GroupingBucketType(graphene.ObjectType):
    """Bucket returned by grouping queries."""

    key = graphene.String(required=True, description="Raw group value")
    label = graphene.String(
        required=True,
        description="Display label for the group (relation name or choice)",
    )
    count = graphene.Int(required=True, description="Record count")


def _resolve_group_by_field(
    model: type[models.Model], path: str
) -> Optional[models.Field]:
    """
    Validate a group_by path against model fields and return the final field if valid.

    Rejects unknown segments and many-to-many paths to avoid ambiguous counts.
    """
    current_model = model
    final_field: Optional[models.Field] = None
    for segment in path.split("__"):
        try:
            final_field = current_model._meta.get_field(segment)
        except FieldDoesNotExist:
            logger.debug(f"Field '{segment}' not found on {current_model.__name__}")
            return None
        if isinstance(final_field, ManyToManyField):
            return None
        if isinstance(final_field, (ForeignKey, OneToOneField)) and getattr(
            final_field, "remote_field", None
        ):
            current_model = final_field.remote_field.model
        else:
            current_model = current_model
    return final_field


def _get_nested_filter_generator(schema_name: str):
    """Lazy import to avoid circular dependencies."""
    from .filter_inputs import NestedFilterInputGenerator
    return NestedFilterInputGenerator(schema_name=schema_name)


def _get_nested_filter_applicator(schema_name: str):
    """Lazy import to avoid circular dependencies."""
    from .filter_inputs import NestedFilterApplicator
    return NestedFilterApplicator(schema_name=schema_name)


def generate_grouping_query(
    self, model: type[models.Model], manager_name: str = "objects"
) -> graphene.Field:
    """
    Generate a lightweight grouping query (counts per value) using the same filter inputs as list queries.

    Returns buckets keyed by the grouped value with a display label and count.
    """
    model_name = model.__name__.lower()
    graphql_meta = get_model_graphql_meta(model)
    filter_class = self.filter_generator.generate_filter_set(model)

    # Generate nested filter input (Prisma/Hasura style)
    nested_where_input = None
    nested_filter_applicator = None
    try:
        nested_generator = _get_nested_filter_generator(self.schema_name)
        nested_where_input = nested_generator.generate_where_input(model)
        nested_filter_applicator = _get_nested_filter_applicator(self.schema_name)
    except (FieldDoesNotExist, ImproperlyConfigured, AttributeError) as e:
        # Expected errors during filter generation (missing fields, bad config)
        logger.warning(
            f"Could not generate nested filter for {model.__name__}: {e}",
            extra={"model": model.__name__, "schema": self.schema_name},
        )
    except RecursionError:
        # Circular reference in model relationships
        logger.error(
            f"Circular reference detected generating filter for {model.__name__}",
            extra={"model": model.__name__},
        )
    except Exception as e:
        # Unexpected error - log with traceback for debugging
        logger.exception(
            f"Unexpected error generating nested filter for {model.__name__}",
            extra={"model": model.__name__, "schema": self.schema_name},
        )

    max_buckets = getattr(self.settings, "max_grouping_buckets", 200) or 200

    @optimize_query()
    def resolver(root: Any, info: graphene.ResolveInfo, **kwargs):
        self._enforce_model_permission(info, model, "list", graphql_meta)
        graphql_meta.ensure_operation_access("list", info=info)

        group_by: Optional[str] = kwargs.get("group_by")
        if not group_by:
            return []

        field = _resolve_group_by_field(model, group_by)
        if field is None:
            return []

        limit = kwargs.get("limit") or max_buckets
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = max_buckets
        limit = max(1, min(limit, max_buckets))

        manager = getattr(model, manager_name)
        queryset = manager.all()
        queryset = self._apply_tenant_scope(
            queryset, info, model, operation="list"
        )

        # Apply query optimization first
        queryset = self.optimizer.optimize_queryset(queryset, info, model)

        # Apply nested 'where' filtering (Prisma/Hasura style)
        where = kwargs.get("where")
        if where and nested_filter_applicator:
            queryset = nested_filter_applicator.apply_where_filter(
                queryset, where, model
            )

        # Apply basic filtering
        basic_filters = {
            k: v
            for k, v in kwargs.items()
            if k
            not in [
                "where",
                "group_by",
                "order_by",
                "limit",
                "include",
            ]
        }
        if basic_filters and filter_class:
            filterset = filter_class(basic_filters, queryset)
            if filterset.is_valid():
                queryset = filterset.qs
            else:
                return []

        value_path = group_by
        queryset = queryset.values(value_path).annotate(total=Count("id"))

        order_by = kwargs.get("order_by") or "group"
        if order_by == "count":
            queryset = queryset.order_by("-total")
        elif order_by == "-count":
            queryset = queryset.order_by("total")
        elif order_by == "-group":
            queryset = queryset.order_by(f"-{value_path}")
        else:
            queryset = queryset.order_by(value_path)

        queryset = queryset[:limit]
        entries = list(queryset)

        related_map = {}
        if (
            isinstance(field, (ForeignKey, OneToOneField))
            and not getattr(field, "choices", None)
        ):
            raw_ids = [entry.get(value_path) for entry in entries]
            related_ids = [raw_id for raw_id in raw_ids if raw_id is not None]
            if related_ids:
                try:
                    related_model = field.remote_field.model
                    related_map = related_model._default_manager.using(queryset.db).in_bulk(
                        related_ids
                    )
                except (AttributeError, TypeError) as e:
                    # Missing remote_field or invalid model access
                    logger.debug(
                        f"Could not fetch related objects for {field.name}: {e}"
                    )
                    related_map = {}

        buckets = []
        for entry in entries:
            raw_value = entry.get(value_path)
            label_value = raw_value
            if getattr(field, "choices", None):
                label_value = dict(field.flatchoices).get(raw_value, raw_value)
            if raw_value is None:
                label_value = str(EMPTY_GROUP_LABEL)
            elif isinstance(field, (ForeignKey, OneToOneField)) and raw_value is not None:
                related_obj = related_map.get(raw_value)
                if related_obj:
                    label_value = str(related_obj)

            buckets.append(
                GroupingBucketType(
                    key="__EMPTY__" if raw_value is None else str(raw_value),
                    label=str(label_value)
                    if label_value is not None
                    else str(EMPTY_GROUP_LABEL),
                    count=int(entry.get("total", 0) or 0),
                )
            )

        return buckets

    arguments = {
        "group_by": graphene.Argument(
            graphene.String,
            required=True,
            description="Field path for grouping (Django-style with __ allowed)",
        ),
        "order_by": graphene.Argument(
            graphene.String,
            required=False,
            description="Ordering: group, -group, count, -count (default: group)",
        ),
        "limit": graphene.Argument(
            graphene.Int,
            required=False,
            description=f"Maximum number of groups (default: {max_buckets}, max: {max_buckets})",
        ),
    }
    if nested_where_input:
        arguments["where"] = graphene.Argument(
            nested_where_input,
            description="Nested filtering with typed field inputs (Prisma/Hasura style)",
        )
    if filter_class:
        for name, field in filter_class.base_filters.items():
            if name == "include":
                field_type = graphene.List(graphene.ID)
            else:
                field_type = self.type_generator.FIELD_TYPE_MAP.get(
                    type(field), graphene.String
                )
            arguments[name] = graphene.Argument(field_type)

    return graphene.Field(
        graphene.List(GroupingBucketType),
        args=arguments,
        resolver=resolver,
        description=f"Grouping counts for {model_name} (manager {manager_name})",
    )
