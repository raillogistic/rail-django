"""
GraphQL queries for Form API.
"""

from __future__ import annotations

from typing import Any, Optional

import graphene
from django.utils import timezone

from ..extractors.base import FormConfigExtractor
from ..codegen.typescript_generator import generate_typescript_definitions
from .types import (
    FormConfigType,
    FormDataType,
    FormModeEnum,
    ModelRefInput,
    TypeDefinitionOutputType,
)


class FormQuery(graphene.ObjectType):
    form_config = graphene.Field(
        FormConfigType,
        app=graphene.String(required=True),
        model=graphene.String(required=True),
        object_id=graphene.ID(),
        mode=FormModeEnum(default_value="CREATE"),
        description="Get complete form configuration for a model.",
    )

    form_data = graphene.Field(
        FormDataType,
        app=graphene.String(required=True),
        model=graphene.String(required=True),
        object_id=graphene.ID(required=True),
        mode=FormModeEnum(default_value="UPDATE"),
        description="Get form configuration plus initial values.",
    )

    form_configs = graphene.List(
        FormConfigType,
        models=graphene.List(ModelRefInput, required=True),
        mode=FormModeEnum(default_value="CREATE"),
        description="Bulk fetch form configs for multiple models.",
    )

    form_type_definitions = graphene.Field(
        TypeDefinitionOutputType,
        models=graphene.List(ModelRefInput, required=True),
        description="Get TypeScript type definitions for models.",
    )

    def resolve_form_config(
        self,
        info,
        app: str,
        model: str,
        object_id: Optional[str] = None,
        mode: str = "CREATE",
    ) -> dict[str, Any]:
        user = getattr(info.context, "user", None)
        extractor = FormConfigExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        return extractor.extract(
            app, model, user=user, object_id=object_id, mode=mode
        )

    def resolve_form_data(
        self,
        info,
        app: str,
        model: str,
        object_id: str,
        mode: str = "UPDATE",
    ) -> dict[str, Any]:
        user = getattr(info.context, "user", None)
        extractor = FormConfigExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        config = extractor.extract(
            app, model, user=user, object_id=object_id, mode=mode
        )
        initial_values = extractor.extract_initial_values(
            app, model, object_id=object_id, user=user
        )
        return {
            "config": config,
            "initial_values": initial_values,
            "readonly_values": None,
        }

    def resolve_form_configs(
        self,
        info,
        models: list[dict[str, str]],
        mode: str = "CREATE",
    ) -> list[dict[str, Any]]:
        user = getattr(info.context, "user", None)
        extractor = FormConfigExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        results = []
        for ref in models or []:
            app = ref.get("app")
            model = ref.get("model")
            if not app or not model:
                continue
            results.append(extractor.extract(app, model, user=user, mode=mode))
        return results

    def resolve_form_type_definitions(
        self,
        info,
        models: list[dict[str, str]],
    ) -> dict[str, Any]:
        user = getattr(info.context, "user", None)
        extractor = FormConfigExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        configs = []
        model_names = []
        for ref in models or []:
            app = ref.get("app")
            model = ref.get("model")
            if not app or not model:
                continue
            configs.append(extractor.extract(app, model, user=user))
            model_names.append(model)

        return {
            "typescript": generate_typescript_definitions(configs),
            "generated_at": timezone.now(),
            "models": model_names,
        }
