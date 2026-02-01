"""
Filter extraction logic for ModelSchemaExtractor.
"""

import json
import logging
from typing import Any, Optional

import graphene
from django.db import models
from django.utils.translation import gettext_lazy as _
from ...utils.graphql_meta import get_model_graphql_meta

logger = logging.getLogger(__name__)

DEFAULT_OPERATORS = {
    "CharField": "icontains",
    "TextField": "icontains",
    "EmailField": "icontains",
    "IntegerField": "eq",
    "SmallIntegerField": "eq",
    "BigIntegerField": "eq",
    "PositiveIntegerField": "eq",
    "FloatField": "eq",
    "DecimalField": "eq",
    "BooleanField": "eq",
    "NullBooleanField": "eq",
    "DateField": "eq",
    "DateTimeField": "gte",
    "TimeField": "eq",
    "ForeignKey": "eq",
    "OneToOneField": "eq",
    "ManyToManyField": "_some",
}

PREFERRED_OPERATORS = {
    "String": ["icontains", "eq", "startsWith", "endsWith", "in"],
    "Number": ["eq", "gte", "lte", "between", "in"],
    "Date": ["eq", "gte", "lte", "between", "year", "month"],
    "DateTime": ["gte", "lte", "between", "eq", "year", "month"],
    "Boolean": ["eq"],
    "Relationship": ["eq", "in", "isNull"],
    "JSON": ["hasKey", "contains", "eq"],
}

DATE_PRESETS = [
    {"key": "today", "label": "Today", "days": 0, "start_of_period": "day"},
    {"key": "yesterday", "label": "Yesterday", "days": -1, "start_of_period": None},
    {"key": "thisWeek", "label": "This Week", "days": 0, "start_of_period": "week"},
    {"key": "lastWeek", "label": "Last Week", "days": -7, "start_of_period": "week"},
    {"key": "thisMonth", "label": "This Month", "days": 0, "start_of_period": "month"},
    {"key": "lastMonth", "label": "Last Month", "days": -30, "start_of_period": "month"},
    {"key": "thisQuarter", "label": "This Quarter", "days": 0, "start_of_period": "quarter"},
    {"key": "thisYear", "label": "This Year", "days": 0, "start_of_period": "year"},
    {"key": "last30Days", "label": "Last 30 Days", "days": -30, "start_of_period": None},
    {"key": "last90Days", "label": "Last 90 Days", "days": -90, "start_of_period": None},
]


class FilterExtractorMixin:
    """Mixin for extracting filters."""

    def extract_model_filters(self, model: type[models.Model]) -> list[dict]:
        """Extract all available filters for a model."""
        filters = []
        try:
            from ...generators.filters import get_nested_filter_generator
            generator = get_nested_filter_generator(self.schema_name)
            where_input_type = generator.generate_where_input(model)

            for field_name, input_field in where_input_type._meta.fields.items():
                if field_name in ["AND", "OR", "NOT"]:
                    continue
                filter_meta = self._analyze_filter_field(model, field_name, input_field)
                if filter_meta:
                    filters.append(filter_meta)
        except Exception as e:
            logger.error(f"Error extracting filters for {model.__name__}: {e}")
        return filters

    def extract_filter_field(
        self, model: type[models.Model], field_name: str
    ) -> Optional[dict]:
        """Extract metadata for a specific filter field."""
        try:
            from ...generators.filters import get_nested_filter_generator
            from graphene.utils.str_converters import to_camel_case

            generator = get_nested_filter_generator(self.schema_name)
            parts = field_name.split(".")

            current_model = model
            current_input_type = generator.generate_where_input(current_model)
            target_input_field = None

            for i, part in enumerate(parts):
                if part not in current_input_type._meta.fields:
                    return None
                target_input_field = current_input_type._meta.fields[part]
                if i < len(parts) - 1:
                    found_model = None
                    for f in current_model._meta.get_fields():
                        if not hasattr(f, "name"):
                            continue
                        camel_name = to_camel_case(f.name)
                        if part == camel_name or part.startswith(camel_name + "_"):
                            if f.is_relation and f.related_model:
                                found_model = f.related_model
                                break
                    if not found_model:
                        return None
                    current_model = found_model
                    current_input_type = generator.generate_where_input(current_model)

            if not target_input_field:
                return None
            return self._analyze_filter_field(current_model, parts[-1], target_input_field)
        except Exception as e:
            logger.error(f"Error extracting filter field {field_name} for {model.__name__}: {e}")
            return None

    def _analyze_filter_field(
        self, model: type[models.Model], field_name: str, input_field: Any
    ) -> Optional[dict]:
        """Analyze a single filter input field and generate its metadata."""
        try:
            from graphene.utils.str_converters import to_camel_case
            input_type = input_field.type
            while hasattr(input_type, "of_type"):
                input_type = input_type.of_type

            type_name = getattr(input_type, "_meta", None) and getattr(
                input_type._meta, "name", None
            )
            if not type_name:
                return None

            available_operators = []
            if hasattr(input_type, "_meta") and hasattr(input_type._meta, "fields"):
                available_operators = [
                    getattr(op_field, "name", None) or op_name
                    for op_name, op_field in input_type._meta.fields.items()
                ]

            model_field = None
            field_label = field_name
            is_nested = False
            related_model_name = None

            candidates = []
            for f in model._meta.get_fields():
                if not hasattr(f, "name"):
                    continue
                camel_name = to_camel_case(f.name)
                if camel_name == field_name:
                    candidates.append((f, 10))
                elif field_name.startswith(camel_name + "_"):
                    candidates.append((f, 5))

            candidates.sort(key=lambda x: x[1], reverse=True)
            if candidates:
                model_field = candidates[0][0]

            if model_field:
                field_label = str(getattr(model_field, "verbose_name", model_field.name))
                is_nested = model_field.is_relation
                if is_nested and model_field.related_model:
                    related_model_name = f"{model_field.related_model._meta.app_label}.{model_field.related_model.__name__}"
                camel_field = to_camel_case(model_field.name)
                if field_name != camel_field:
                    suffix = field_name.replace(camel_field, "")
                    if suffix == "_some":
                        field_label += f" ({_('At least one')})"
                    elif suffix == "_every":
                        field_label += f" ({_('All')})"
                    elif suffix == "_none":
                        field_label += f" ({_('None')})"
                    elif suffix == "_count":
                        field_label += f" ({_('Count')})"
                    elif suffix == "_agg":
                        field_label += f" ({_('Aggregation')})"
                    elif suffix == "_trunc":
                        field_label += f" ({_('Truncated date')})"
                    elif suffix == "_extract":
                        field_label += f" ({_('Date extraction')})"
            else:
                labels = {
                    "id": "ID",
                    "quick": _("Quick search"),
                    "search": _("Full text search"),
                    "_window": _("Window filter"),
                    "_subquery": _("Subquery filter"),
                    "_exists": _("Existence filter"),
                    "_compare": _("Field comparison"),
                    "include": _("Include IDs"),
                    "instanceIn": _("Source instances"),
                    "historyTypeIn": _("History type"),
                }
                field_label = labels.get(field_name, field_name)

            # Base type mapping for UI widgets
            base_type = "String"
            if model_field:
                internal_type = model_field.get_internal_type()
                if internal_type in (
                    "IntegerField",
                    "SmallIntegerField",
                    "BigIntegerField",
                    "PositiveIntegerField",
                    "FloatField",
                    "DecimalField",
                ):
                    base_type = "Number"
                elif internal_type in ("BooleanField", "NullBooleanField"):
                    base_type = "Boolean"
                elif internal_type == "DateField":
                    base_type = "Date"
                elif internal_type == "DateTimeField":
                    base_type = "DateTime"
                elif internal_type == "TimeField":
                    base_type = "Date"
                elif internal_type in ("ForeignKey", "OneToOneField", "ManyToManyField"):
                    base_type = "Relationship"
                elif internal_type == "JSONField":
                    base_type = "JSON"

            options = []
            if hasattr(input_type, "_meta") and hasattr(input_type._meta, "fields"):
                # Operator labels
                operator_labels = {
                    "eq": _("Equals"),
                    "neq": _("Different from"),
                    "contains": _("Contains"),
                    "icontains": _("Contains (case-insensitive)"),
                    "in": _("In list"),
                    "notIn": _("Not in list"),
                    "gt": _("Greater than"),
                    "gte": _("Greater than or equal to"),
                    "lt": _("Less than"),
                    "lte": _("Less than or equal to"),
                    "startsWith": _("Starts with"),
                    "endsWith": _("Ends with"),
                    "regex": _("Regex match"),
                    "isNull": _("Is null"),
                    "hasKey": _("Has key"),
                    "hasKeys": _("Has keys"),
                    "hasAnyKeys": _("Has any keys"),
                    # Date specific
                    "year": _("Year"),
                    "month": _("Month"),
                    "day": _("Day"),
                    "weekDay": _("Day of week"),
                    "hour": _("Hour"),
                    "minute": _("Minute"),
                    "second": _("Second"),
                    "range": _("Range"),
                }

                for op_name, op_field in input_type._meta.fields.items():
                    graphql_name = getattr(op_field, "name", None) or op_name
                    op_type = op_field.type
                    is_list = False
                    temp_type = op_type
                    while hasattr(temp_type, "of_type"):
                        if isinstance(temp_type, graphene.List):
                            is_list = True
                        temp_type = temp_type.of_type
                    op_graphql_type = (getattr(temp_type, "_meta", None) and getattr(temp_type._meta, "name", None)) or str(temp_type)
                    field_choices = None
                    if model_field and hasattr(model_field, "choices") and model_field.choices:
                        if graphql_name in ("eq", "in", "neq", "notIn"):
                            field_choices = [{"value": str(c[0]), "label": str(c[1])} for c in model_field.choices]

                    op_label = operator_labels.get(graphql_name, graphql_name)
                    options.append({
                        "name": graphql_name,
                        "lookup": graphql_name,
                        "label": str(op_label),
                        "help_text": graphql_name,
                        "choices": field_choices,
                        "graphql_type": op_graphql_type,
                        "is_list": is_list
                    })

            return {
                "name": to_camel_case(field_name),
                "field_name": field_name,
                "field_label": field_label,
                "base_type": base_type,
                "is_nested": is_nested,
                "related_model": related_model_name,
                "options": options,
                "filter_input_type": type_name,
                "available_operators": available_operators,
                "default_operator": self._get_default_operator(
                    model_field, base_type, available_operators
                ),
                "preferred_operators": self._get_preferred_operators(
                    base_type, available_operators
                ),
                "date_presets": self._get_date_presets(base_type),
                "show_in_quick_filter": self._get_show_in_quick_filter(model_field),
                "priority": self._get_field_priority(model, model_field),
            }
        except Exception as e:
            logger.warning(f"Error analyzing filter field {field_name} for {model.__name__}: {e}")
            return None

    def _extract_filters(self, model: type[models.Model]) -> list[dict]:
        """Extract available filters."""
        return self.extract_model_filters(model)

    def _extract_filter_config(self, model: type[models.Model]) -> dict:
        """Extract filter configuration for the model."""
        model_name = model.__name__
        presets = []
        computed_filters = []
        supports_fts = False
        try:
            graphql_meta = get_model_graphql_meta(model)
            if graphql_meta:
                if graphql_meta.filter_presets:
                    from graphene.utils.str_converters import to_camel_case
                    for name, definition in graphql_meta.filter_presets.items():
                        presets.append({
                            "name": to_camel_case(name),
                            "preset_name": name,
                            "description": f"Preset: {name}",
                            "filter_json": json.dumps(definition)
                        })
                if hasattr(graphql_meta, "computed_filters") and graphql_meta.computed_filters:
                    from graphene.utils.str_converters import to_camel_case
                    for name, definition in graphql_meta.computed_filters.items():
                        computed_filters.append({
                            "name": to_camel_case(name),
                            "field_name": name,
                            "filter_type": definition.get("filter_type", "string"),
                            "description": definition.get("description", "")
                        })
            try:
                from ...core.settings import FilteringSettings
                filtering_settings = FilteringSettings.from_schema(self.schema_name)
                supports_fts = getattr(filtering_settings, "enable_full_text_search", False)
            except Exception: pass
        except Exception: pass

        return {
            "style": "NESTED",
            "argument_name": "where",
            "input_type_name": f"{model_name}WhereInput",
            "supports_and": True,
            "supports_or": True,
            "supports_not": True,
            "dual_mode_enabled": False,
            "supports_fts": supports_fts,
            "supports_aggregation": True,
            "presets": presets,
            "computed_filters": computed_filters,
        }

    def _extract_relation_filters(
        self, model: type[models.Model], include_nested_schema: bool = False, depth: int = 0, max_depth: int = 2
    ) -> list[dict]:
        """Extract relation filter metadata with optional nested schema support.

        Args:
            model: The Django model to extract relations from.
            include_nested_schema: Whether to include nested field/operator info.
            depth: Current recursion depth.
            max_depth: Maximum recursion depth for nested schemas.
        """
        relation_filters = []
        for field in model._meta.get_fields():
            if not hasattr(field, "name"): continue
            is_fk = isinstance(field, models.ForeignKey)
            is_o2o = isinstance(field, models.OneToOneField)
            is_m2m = isinstance(field, models.ManyToManyField)
            is_reverse = hasattr(field, "related_model") and not hasattr(field, "remote_field")
            is_reverse_m2m = hasattr(field, "many_to_many") and field.many_to_many
            is_reverse_fk = hasattr(field, "one_to_many") and field.one_to_many

            if not (is_fk or is_o2o or is_m2m or is_reverse_m2m or is_reverse_fk):
                continue

            related_model = getattr(field, "related_model", None)
            if not related_model:
                continue

            # Determine relation type
            if is_fk:
                relation_type = "FOREIGN_KEY"
            elif is_o2o:
                relation_type = "ONE_TO_ONE"
            elif is_m2m or is_reverse_m2m:
                relation_type = "MANY_TO_MANY"
            else:
                relation_type = "REVERSE_FK"

            from graphene.utils.str_converters import to_camel_case

            relation_data = {
                "name": to_camel_case(field.name),
                "field_name": field.name,
                "field_label": str(getattr(field, "verbose_name", field.name)),
                "relation_type": relation_type,
                "related_app": related_model._meta.app_label,
                "related_model": related_model.__name__,
                "supports_direct_filter": relation_type in ("FOREIGN_KEY", "ONE_TO_ONE"),
                "supports_some": relation_type in ("MANY_TO_MANY", "REVERSE_FK"),
                "supports_every": relation_type in ("MANY_TO_MANY", "REVERSE_FK"),
                "supports_none": relation_type in ("MANY_TO_MANY", "REVERSE_FK"),
                "supports_count": relation_type in ("MANY_TO_MANY", "REVERSE_FK"),
                "supports_is_null": relation_type == "FOREIGN_KEY",
                "nested_filter_type": f"{related_model.__name__}WhereInput",
            }

            # Include nested schema if requested and within depth limit
            if include_nested_schema and depth < max_depth:
                try:
                    nested_fields = self._extract_nested_filter_fields(
                        related_model, depth + 1, max_depth
                    )
                    relation_data["nested_fields"] = nested_fields
                except Exception as e:
                    logger.debug(f"Could not extract nested schema for {field.name}: {e}")

            relation_filters.append(relation_data)
        return relation_filters

    def _extract_nested_filter_fields(
        self, model: type[models.Model], depth: int = 0, max_depth: int = 2
    ) -> list[dict]:
        """Extract a lightweight version of filter fields for nested relations.

        This provides just enough information for the frontend to render
        field selectors without requiring a full schema fetch.
        """
        from graphene.utils.str_converters import to_camel_case

        fields = []
        for field in model._meta.get_fields():
            if not hasattr(field, "name"):
                continue
            if field.name.startswith("_") or "polymorphic" in field.name.lower():
                continue

            # Skip reverse relations at this level (too complex for lightweight extraction)
            if hasattr(field, "related_model") and not hasattr(field, "remote_field"):
                continue

            field_name = field.name
            verbose_name = str(getattr(field, "verbose_name", field_name))

            # Determine base type
            base_type = "String"
            is_relation = False
            if hasattr(field, "get_internal_type"):
                internal_type = field.get_internal_type()
                if internal_type in (
                    "IntegerField", "SmallIntegerField", "BigIntegerField",
                    "PositiveIntegerField", "FloatField", "DecimalField",
                ):
                    base_type = "Number"
                elif internal_type in ("BooleanField", "NullBooleanField"):
                    base_type = "Boolean"
                elif internal_type == "DateField":
                    base_type = "Date"
                elif internal_type == "DateTimeField":
                    base_type = "DateTime"
                elif internal_type in ("ForeignKey", "OneToOneField", "ManyToManyField"):
                    base_type = "Relationship"
                    is_relation = True
                elif internal_type == "JSONField":
                    base_type = "JSON"

            field_data = {
                "name": to_camel_case(field_name),
                "field_name": field_name,
                "field_label": verbose_name,
                "base_type": base_type,
                "is_relation": is_relation,
            }

            # Add relation info if it's a relation field
            if is_relation and hasattr(field, "related_model") and field.related_model:
                related = field.related_model
                field_data["related_app"] = related._meta.app_label
                field_data["related_model"] = related.__name__

            # Get default operator
            default_op = self._get_default_operator(
                field if hasattr(field, "get_internal_type") else None,
                base_type,
                PREFERRED_OPERATORS.get(base_type, ["eq"])
            )
            field_data["default_operator"] = default_op
            field_data["preferred_operators"] = PREFERRED_OPERATORS.get(base_type, ["eq"])

            fields.append(field_data)

        return fields

    def extract_relation_filters_with_depth(
        self, model: type[models.Model], max_depth: int = 2
    ) -> list[dict]:
        """Extract relation filters with nested schema information up to max_depth.

        This is used by the GraphQL schema to provide nested field information
        for lazy loading in the frontend.
        """
        return self._extract_relation_filters(
            model, include_nested_schema=True, depth=0, max_depth=max_depth
        )

    def _get_default_operator(
        self,
        model_field: Optional[models.Field],
        base_type: str,
        available_operators: list[str],
    ) -> str:
        if model_field:
            default = DEFAULT_OPERATORS.get(model_field.get_internal_type())
            if default and default in available_operators:
                return default
        preferred = PREFERRED_OPERATORS.get(base_type, [])
        for operator in preferred:
            if operator in available_operators:
                return operator
        return available_operators[0] if available_operators else "eq"

    def _get_preferred_operators(
        self, base_type: str, available_operators: list[str]
    ) -> list[str]:
        preferred = PREFERRED_OPERATORS.get(base_type, [])
        ordered = [op for op in preferred if op in available_operators]
        ordered += [op for op in available_operators if op not in ordered]
        return ordered

    def _get_date_presets(self, base_type: str) -> Optional[list[dict]]:
        if base_type not in ("Date", "DateTime"):
            return None
        return DATE_PRESETS

    def _get_show_in_quick_filter(
        self, model_field: Optional[models.Field]
    ) -> bool:
        if not model_field:
            return False
        if getattr(model_field, "primary_key", False):
            return True
        field_name = model_field.name.lower()
        return field_name in {
            "name",
            "title",
            "status",
            "state",
            "created_at",
            "created",
            "updated_at",
            "updated",
            "date",
            "type",
        }

    def _get_field_priority(
        self, model: type[models.Model], model_field: Optional[models.Field]
    ) -> int:
        if not model_field:
            return 999
        try:
            for index, field in enumerate(model._meta.fields):
                if field is model_field:
                    return index
        except Exception:
            pass
        return 999
