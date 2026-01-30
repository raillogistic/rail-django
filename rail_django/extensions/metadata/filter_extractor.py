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
                available_operators = list(input_type._meta.fields.keys())

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
                if internal_type in ("IntegerField", "SmallIntegerField", "BigIntegerField", "PositiveIntegerField", "FloatField", "DecimalField"):
                    base_type = "Number"
                elif internal_type in ("BooleanField", "NullBooleanField"):
                    base_type = "Boolean"
                elif internal_type in ("DateField", "DateTimeField", "TimeField"):
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
                        if op_name in ("eq", "in", "neq", "notIn"):
                            field_choices = [{"value": str(c[0]), "label": str(c[1])} for c in model_field.choices]

                    op_label = operator_labels.get(op_name, op_name)
                    options.append({
                        "name": op_name,
                        "lookup": op_name,
                        "label": str(op_label),
                        "help_text": op_name,
                        "choices": field_choices,
                        "graphql_type": op_graphql_type,
                        "is_list": is_list
                    })

            return {
                "field_name": field_name,
                "field_label": field_label,
                "base_type": base_type,
                "is_nested": is_nested,
                "related_model": related_model_name,
                "options": options,
                "filter_input_type": type_name,
                "available_operators": available_operators,
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
                    for name, definition in graphql_meta.filter_presets.items():
                        presets.append({"name": name, "description": f"Preset: {name}", "filter_json": json.dumps(definition)})
                if hasattr(graphql_meta, "computed_filters") and graphql_meta.computed_filters:
                    for name, definition in graphql_meta.computed_filters.items():
                        computed_filters.append({"name": name, "filter_type": definition.get("filter_type", "string"), "description": definition.get("description", "")})
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

    def _extract_relation_filters(self, model: type[models.Model]) -> list[dict]:
        """Extract relation filter metadata."""
        relation_filters = []
        for field in model._meta.get_fields():
            if not hasattr(field, "name"): continue
            is_m2m = isinstance(field, models.ManyToManyField)
            is_reverse = hasattr(field, "related_model") and not hasattr(field, "remote_field")
            is_reverse_m2m = hasattr(field, "many_to_many") and field.many_to_many
            is_reverse_fk = hasattr(field, "one_to_many") and field.one_to_many
            if is_m2m or is_reverse_m2m or is_reverse_fk:
                related_model = getattr(field, "related_model", None)
                if not related_model: continue
                relation_type = "MANY_TO_MANY" if (is_m2m or is_reverse_m2m) else "REVERSE_FK"
                relation_filters.append({
                    "relation_name": field.name,
                    "relation_type": relation_type,
                    "supports_some": True, "supports_every": True, "supports_none": True, "supports_count": True,
                    "nested_filter_type": f"{related_model.__name__}WhereInput",
                })
        return relation_filters
