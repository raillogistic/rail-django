"""
Grouping query builders.
"""

from typing import Any, Optional, Type

import graphene
from django.db import models
from django.db.models import Count, ForeignKey, ManyToManyField, OneToOneField

from ..core.meta import get_model_graphql_meta
from ..extensions.optimization import optimize_query


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
        except Exception:
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
    complex_filter_input = self.filter_generator.generate_complex_filter_input(
        model
    )
    max_buckets = getattr(self.settings, "max_grouping_buckets", 200) or 200

    @optimize_query()
    def resolver(root: Any, info: graphene.ResolveInfo, **kwargs):
        group_by: Optional[str] = kwargs.get("group_by")
        if not group_by:
            return []

        field = _resolve_group_by_field(model, group_by)
        if field is None:
            return []

        limit = kwargs.get("limit") or max_buckets
        try:
            limit = int(limit)
        except Exception:
            limit = max_buckets
        limit = max(1, min(limit, max_buckets))

        manager = getattr(model, manager_name)
        queryset = manager.all()
        graphql_meta.ensure_operation_access("list", info=info)

        # Apply query optimization first
        queryset = self.optimizer.optimize_queryset(queryset, info, model)

        # Apply advanced filtering
        filters = kwargs.get("filters")
        if filters:
            queryset = self.filter_generator.apply_complex_filters(
                queryset, filters
            )

        # Apply basic filtering
        basic_filters = {
            k: v
            for k, v in kwargs.items()
            if k
            not in [
                "filters",
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
                except Exception:
                    related_map = {}

        buckets = []
        for entry in entries:
            raw_value = entry.get(value_path)
            label_value = raw_value
            if getattr(field, "choices", None):
                label_value = dict(field.flatchoices).get(raw_value, raw_value)
            if raw_value is None:
                label_value = "Non renseignǸ"
            elif isinstance(field, (ForeignKey, OneToOneField)) and raw_value is not None:
                related_obj = related_map.get(raw_value)
                if related_obj:
                    label_value = str(related_obj)

            buckets.append(
                GroupingBucketType(
                    key="__EMPTY__" if raw_value is None else str(raw_value),
                    label=str(label_value)
                    if label_value is not None
                    else "Non renseignǸ",
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
    if complex_filter_input:
        arguments["filters"] = graphene.Argument(
            complex_filter_input,
            description="Advanced filters shared with list queries",
        )
    if filter_class:
        for name, field in filter_class.base_filters.items():
            arguments[name] = graphene.Argument(
                self.type_generator.FIELD_TYPE_MAP.get(
                    type(field), graphene.String
                )
            )

    return graphene.Field(
        graphene.List(GroupingBucketType),
        args=arguments,
        resolver=resolver,
        description=f"Grouping counts for {model_name} (manager {manager_name})",
    )
