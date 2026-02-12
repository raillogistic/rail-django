"""
GraphQL queries for Form API.
"""

from __future__ import annotations

from typing import Any, Optional

import graphene
from django.utils import timezone
from django.apps import apps
from graphql import GraphQLError

from ..extractors.base import FormConfigExtractor
from ..extractors.model_form_contract_extractor import ModelFormContractExtractor
from ..config import is_generated_form_enabled
from ..codegen.typescript_generator import generate_typescript_definitions
from .types import (
    FormConfigType,
    FormDataType,
    FormModeEnum,
    ModelFormContractPageType,
    ModelFormContractType,
    ModelFormInitialDataType,
    ModelFormModeEnum,
    ModelFormRuntimeOverrideInput,
    ModelRefContractInput,
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

    model_form_contract = graphene.Field(
        ModelFormContractType,
        app_label=graphene.String(required=True, name="appLabel"),
        model_name=graphene.String(required=True, name="modelName"),
        mode=ModelFormModeEnum(default_value="CREATE"),
        include_nested=graphene.Boolean(default_value=False, name="includeNested"),
        description="Get generated model-form contract for one model.",
    )

    model_form_contract_pages = graphene.Field(
        ModelFormContractPageType,
        page=graphene.Int(default_value=1),
        per_page=graphene.Int(default_value=50, name="perPage"),
        models=graphene.List(ModelRefContractInput),
        mode=ModelFormModeEnum(default_value="CREATE"),
        include_nested=graphene.Boolean(default_value=False, name="includeNested"),
        description="Get paginated generated model-form contracts for enabled models.",
    )

    model_form_initial_data = graphene.Field(
        ModelFormInitialDataType,
        app_label=graphene.String(required=True, name="appLabel"),
        model_name=graphene.String(required=True, name="modelName"),
        object_id=graphene.ID(required=True, name="objectId"),
        include_nested=graphene.Boolean(default_value=False, name="includeNested"),
        runtime_overrides=graphene.List(
            ModelFormRuntimeOverrideInput,
            name="runtimeOverrides",
        ),
        description="Get generated model-form initial data payload.",
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

    def resolve_model_form_contract(
        self,
        info,
        app_label: str,
        model_name: str,
        mode: str = "CREATE",
        include_nested: bool = False,
    ) -> dict[str, Any]:
        extractor = ModelFormContractExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        user = getattr(info.context, "user", None)
        return extractor.extract_contract(
            app_label,
            model_name,
            user=user,
            mode=mode,
            include_nested=include_nested,
            enforce_opt_in=True,
        )

    def resolve_model_form_contract_pages(
        self,
        info,
        page: int = 1,
        per_page: int = 50,
        models: Optional[list[dict[str, str]]] = None,
        mode: str = "CREATE",
        include_nested: bool = False,
    ) -> dict[str, Any]:
        extractor = ModelFormContractExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        user = getattr(info.context, "user", None)

        model_refs = models
        if not model_refs:
            model_refs = []
            for model in apps.get_models():
                if is_generated_form_enabled(model):
                    model_refs.append(
                        {
                            "app_label": model._meta.app_label,
                            "model_name": model.__name__,
                        }
                    )

        return extractor.extract_contract_page(
            model_refs,
            user=user,
            mode=mode,
            include_nested=include_nested,
            page=page,
            per_page=per_page,
        )

    def resolve_model_form_initial_data(
        self,
        info,
        app_label: str,
        model_name: str,
        object_id: str,
        include_nested: bool = False,
        runtime_overrides: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        extractor = ModelFormContractExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        user = getattr(info.context, "user", None)

        # Keep explicit guard and message to drive frontend fallback decisions.
        model = apps.get_model(app_label, model_name)
        if not is_generated_form_enabled(model):
            raise GraphQLError(
                f"Generated form contract is not enabled for '{app_label}.{model_name}'."
            )

        return extractor.extract_initial_data_payload(
            app_label,
            model_name,
            object_id=object_id,
            user=user,
            include_nested=include_nested,
            runtime_overrides=runtime_overrides or [],
        )
