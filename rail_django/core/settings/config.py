"""
GraphQLAutoConfig implementation.
"""

from typing import List, Optional
from .type_settings import TypeGeneratorSettings
from .query_settings import QueryGeneratorSettings
from .mutation_settings import MutationGeneratorSettings
from .schema_settings import SchemaSettings


class GraphQLAutoConfig:
    """Configuration class for managing model-specific GraphQL auto-generation settings."""

    def __init__(
        self,
        type_settings: Optional[TypeGeneratorSettings] = None,
        query_settings: Optional[QueryGeneratorSettings] = None,
        mutation_settings: Optional[MutationGeneratorSettings] = None,
        schema_settings: Optional[SchemaSettings] = None,
    ):
        self.type_settings = type_settings or TypeGeneratorSettings()
        self.query_settings = query_settings or QueryGeneratorSettings()
        self.mutation_settings = mutation_settings or MutationGeneratorSettings()
        self.schema_settings = schema_settings or SchemaSettings()

    def should_include_model(self, model_name: str) -> bool:
        return (model_name not in self.schema_settings.excluded_models and model_name not in self.schema_settings.excluded_apps)

    def should_include_field(self, model_name: str, field_name: str) -> bool:
        excluded = set(self.type_settings.exclude_fields.get(model_name, [])) | set(self.type_settings.excluded_fields.get(model_name, []))
        if field_name in excluded: return False
        if self.type_settings.include_fields is not None:
            return field_name in self.type_settings.include_fields.get(model_name, [])
        return True

    def get_additional_lookup_fields(self, model_name: str) -> List[str]:
        return self.query_settings.additional_lookup_fields.get(model_name, [])
