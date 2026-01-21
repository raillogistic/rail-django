"""
Filter extraction logic for ModelSchemaExtractor.
"""

import json
import logging
from typing import Any, Optional

import graphene
from django.db import models
from ...utils.graphql_meta import get_model_graphql_meta

logger = logging.getLogger(__name__)


class FilterExtractorMixin:
    """Mixin for extracting filters."""

    def extract_model_filters(self, model: type[models.Model]) -> list[dict]:
        """Extract all available filters for a model."""
        filters = []
        try:
            from ...generators.filter_inputs import get_nested_filter_generator
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
            from ...generators.filter_inputs import get_nested_filter_generator
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
                    if suffix == "_some": field_label += " (Au moins un)"
                    elif suffix == "_every": field_label += " (Tous)"
                    elif suffix == "_none": field_label += " (Aucun)"
                    elif suffix == "_count": field_label += " (Compte)"
                    elif suffix == "_agg": field_label += " (AgrÇ¸gation)"
            else:
                labels = {
                    "id": "ID", "quick": "Recherche rapide", "search": "Recherche texte intÇ¸gral",
                    "_window": "Filtre fenÇºtre", "_subquery": "Filtre sous-requÇºte",
                    "_exists": "Filtre existence", "_compare": "Comparaison champs",
                    "include": "Inclure IDs", "instanceIn": "Instances d'origine",
                    "historyTypeIn": "Type d'historique",
                }
                field_label = labels.get(field_name, field_name)

            options = []
            if hasattr(input_type, "_meta") and hasattr(input_type._meta, "fields"):
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
                    options.append({"name": op_name, "lookup": op_name, "help_text": op_name, "choices": field_choices, "graphql_type": op_graphql_type, "is_list": is_list})

            return {
                "field_name": field_name,
                "field_label": field_label,
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
