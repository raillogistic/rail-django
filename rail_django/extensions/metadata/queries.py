"""
GraphQL Queries for Metadata V2.
"""

import logging
from typing import Optional

import graphene
from django.apps import apps
from graphene.utils.str_converters import to_camel_case, to_snake_case
from graphql import GraphQLError
from graphql.language import ast

from .extractor import ModelSchemaExtractor
from .detail_extractor import DetailContractExtractor
from ...core.meta import get_model_graphql_meta
from .types import (
    DetailContractInputType,
    DetailContractResultType,
    FilterSchemaType,
    FrontendRouteAccessManifestType,
    ModelInfoType,
    ModelSchemaType,
    MutationSchemaType,
    TemplateInfoType,
)
from ...security.frontend_routes import frontend_route_access_registry

logger = logging.getLogger(__name__)


def _describe_discovery_state(model, user) -> list[dict]:
    try:
        graphql_meta = get_model_graphql_meta(model)
    except Exception:
        return []

    describe = getattr(graphql_meta, "describe_operation_guard", None)
    if not callable(describe):
        return []

    states: list[dict] = []
    for operation in ("list", "retrieve"):
        try:
            state = describe(operation, user=user, instance=None)
        except Exception:
            continue
        if isinstance(state, dict):
            states.append(state)
    return states


def _user_can_discover_model(model, user) -> bool:
    if user and getattr(user, "is_superuser", False):
        return True

    states = _describe_discovery_state(model, user)
    guarded_states = [state for state in states if state.get("guarded")]
    guarded_allows = any(state.get("allowed", False) for state in guarded_states)

    has_view_perm = False
    has_perm = getattr(user, "has_perm", None)
    if callable(has_perm):
        perm_name = f"{model._meta.app_label}.view_{model._meta.model_name}"
        try:
            has_view_perm = bool(has_perm(perm_name))
        except Exception:
            has_view_perm = False

    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    if not is_authenticated:
        # Anonymous users can only discover models explicitly allowed by guards.
        return guarded_allows

    if guarded_states and not guarded_allows:
        return False

    return has_view_perm or guarded_allows


def _collect_requested_subfields(info) -> set[str]:
    """Return requested top-level subfields for the current GraphQL field."""

    requested: set[str] = set()
    fragments = getattr(info, "fragments", {}) or {}

    def visit_selection_set(selection_set) -> None:
        if not selection_set:
            return
        for selection in selection_set.selections:
            if isinstance(selection, ast.FieldNode):
                field_name = selection.name.value
                if field_name and field_name != "__typename":
                    requested.add(to_snake_case(field_name))
            elif isinstance(selection, ast.InlineFragmentNode):
                visit_selection_set(selection.selection_set)
            elif isinstance(selection, ast.FragmentSpreadNode):
                fragment = fragments.get(selection.name.value)
                if fragment:
                    visit_selection_set(fragment.selection_set)

    for field_node in getattr(info, "field_nodes", []) or []:
        visit_selection_set(field_node.selection_set)

    return requested


def _collect_requested_section_subfields(info) -> dict[str, set[str]]:
    """
    Return requested nested subfields per top-level section.

    Example output:
      {
          "fields": {"name", "field_name", "visibility"},
          "relationships": {"name", "related_model"}
      }
    """

    requested: dict[str, set[str]] = {}
    fragments = getattr(info, "fragments", {}) or {}

    def record(section: str, field_name: str) -> None:
        if not section or not field_name or field_name == "__typename":
            return
        requested.setdefault(section, set()).add(to_snake_case(field_name))

    def visit_selection_set(
        selection_set, active_section: Optional[str] = None
    ) -> None:
        if not selection_set:
            return
        for selection in selection_set.selections:
            if isinstance(selection, ast.FieldNode):
                field_name = selection.name.value
                if field_name == "__typename":
                    continue

                if active_section is None:
                    section_name = to_snake_case(field_name)
                    if selection.selection_set:
                        visit_selection_set(selection.selection_set, section_name)
                    continue

                record(active_section, field_name)
                if selection.selection_set:
                    # Keep collecting under the same top-level section.
                    visit_selection_set(selection.selection_set, active_section)
            elif isinstance(selection, ast.InlineFragmentNode):
                visit_selection_set(selection.selection_set, active_section)
            elif isinstance(selection, ast.FragmentSpreadNode):
                fragment = fragments.get(selection.name.value)
                if fragment:
                    visit_selection_set(fragment.selection_set, active_section)

    for field_node in getattr(info, "field_nodes", []) or []:
        visit_selection_set(field_node.selection_set)

    return requested


class ModelSchemaQuery(graphene.ObjectType):
    """
    GraphQL queries for model schema (Metadata V2).

    Provides comprehensive model introspection for frontend UI generation.
    """

    modelSchema = graphene.Field(
        ModelSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        objectId=graphene.ID(
            description="Instance ID for instance-specific permissions"
        ),
        description="Get complete schema information for a model.",
    )

    customMutation = graphene.Field(
        MutationSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        function_name=graphene.String(
            required=True, description="Custom mutation function name"
        ),
        objectId=graphene.ID(
            description="Instance ID for instance-specific permissions"
        ),
        description="Get metadata for one custom model mutation.",
    )

    modelTemplate = graphene.Field(
        TemplateInfoType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        function_name=graphene.String(
            required=True, description="Model template function name"
        ),
        objectId=graphene.ID(
            description="Instance ID for instance-specific permissions"
        ),
        description="Get metadata for one model template.",
    )

    modelDetailContract = graphene.Field(
        DetailContractResultType,
        input=DetailContractInputType(required=True),
        description=(
            "Resolve metadata-driven detail contract for one model and optional "
            "record scope."
        ),
    )

    availableModels = graphene.List(
        ModelInfoType,
        app=graphene.String(description="Filter by app"),
        description="List all available models.",
    )

    appSchemas = graphene.List(
        ModelSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        description="Get schemas for all models in an app.",
    )

    filterSchema = graphene.List(
        FilterSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        description="Get all available filters for a model",
    )

    fieldFilterSchema = graphene.Field(
        FilterSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        field=graphene.String(required=True, description="Filter field name"),
        description="Get filter metadata for a specific field",
    )

    metadataDeployVersion = graphene.String(
        key=graphene.String(description="Deployment version key"),
        description="Deployment-level metadata version for cache invalidation.",
    )

    frontendRouteAccess = graphene.Field(
        FrontendRouteAccessManifestType,
        description=(
            "Resolved frontend route access rules for the current user. "
            "Intended for route and navigation visibility only."
        ),
    )

    @staticmethod
    def _identifier_matches(target: str, *candidates: Optional[str]) -> bool:
        def _forms(value: Optional[str]) -> set[str]:
            raw = str(value or "").strip()
            if not raw:
                return set()
            snake = to_snake_case(raw)
            camel = to_camel_case(snake)
            compact = snake.replace("_", "").lower()
            return {
                raw.lower(),
                snake.lower(),
                camel.lower(),
                compact,
            }

        wanted = _forms(target)
        if not wanted:
            return False

        for candidate in candidates:
            if wanted & _forms(candidate):
                return True
        return False

    @staticmethod
    def _template_method_index(model_cls: type) -> dict[str, set[str]]:
        method_index: dict[str, set[str]] = {}

        from ..templating.registry import template_registry

        for url_path, definition in template_registry.all().items():
            if getattr(definition, "model", None) != model_cls:
                continue
            method_name = getattr(definition, "method_name", None)
            if not method_name:
                continue
            method_index.setdefault(str(url_path), set()).add(str(method_name))

        try:
            from ..excel.exporter import excel_template_registry
        except Exception:
            excel_template_registry = None

        if excel_template_registry:
            for url_path, definition in excel_template_registry.all().items():
                if getattr(definition, "model", None) != model_cls:
                    continue
                method_name = getattr(definition, "method_name", None)
                if not method_name:
                    continue
                method_index.setdefault(str(url_path), set()).add(str(method_name))

        return method_index

    def resolve_modelSchema(
        self,
        info,
        app: str,
        model: str,
        objectId: Optional[str] = None,
    ) -> dict:
        """
        Resolve complete model schema.

        Args:
            info: GraphQL resolve info.
            app: Django app label.
            model: Model name.
            objectId: Optional instance ID.

        Returns:
            Complete model schema.
        """
        user = getattr(info.context, "user", None)
        try:
            model_cls = apps.get_model(app, model)
        except LookupError:
            raise GraphQLError(f"Model '{app}.{model}' not found.")
        if not _user_can_discover_model(model_cls, user):
            raise GraphQLError("Access denied")

        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        requested_sections = _collect_requested_subfields(info)
        requested_section_subfields = _collect_requested_section_subfields(info)
        return extractor.extract(
            app,
            model,
            user=user,
            object_id=objectId,
            include_sections=requested_sections,
            include_section_subfields=requested_section_subfields,
        )

    def resolve_customMutation(
        self,
        info,
        app: str,
        model: str,
        function_name: str,
        objectId: Optional[str] = None,
    ) -> Optional[dict]:
        user = getattr(info.context, "user", None)
        try:
            model_cls = apps.get_model(app, model)
        except LookupError:
            raise GraphQLError(f"Model '{app}.{model}' not found.")
        if not _user_can_discover_model(model_cls, user):
            raise GraphQLError("Access denied")

        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        schema = extractor.extract(
            app,
            model,
            user=user,
            object_id=objectId,
            include_sections={"mutations"},
        )

        for mutation in schema.get("mutations", []):
            if not isinstance(mutation, dict):
                continue
            if mutation.get("operation") != "custom":
                continue
            if self._identifier_matches(
                function_name,
                mutation.get("method_name"),
                mutation.get("name"),
            ):
                return mutation
        return None

    def resolve_modelTemplate(
        self,
        info,
        app: str,
        model: str,
        function_name: str,
        objectId: Optional[str] = None,
    ) -> Optional[dict]:
        user = getattr(info.context, "user", None)
        try:
            model_cls = apps.get_model(app, model)
        except LookupError:
            raise GraphQLError(f"Model '{app}.{model}' not found.")
        if not _user_can_discover_model(model_cls, user):
            raise GraphQLError("Access denied")

        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        schema = extractor.extract(
            app,
            model,
            user=user,
            object_id=objectId,
            include_sections={"templates"},
        )
        template_methods = self._template_method_index(model_cls)

        for template in schema.get("templates", []):
            if not isinstance(template, dict):
                continue
            key = str(template.get("key") or "")
            url_path = str(template.get("url_path") or "")
            candidates = [
                key,
                url_path,
                key.rsplit("/", 1)[-1] if key else "",
                url_path.rsplit("/", 1)[-1] if url_path else "",
            ]
            candidates.extend(template_methods.get(key, ()))
            candidates.extend(template_methods.get(url_path, ()))
            if self._identifier_matches(function_name, *candidates):
                return template
        return None

    def resolve_modelDetailContract(self, info, input: dict) -> dict:
        user = getattr(info.context, "user", None)
        app = str(input.get("app") or "")
        model = str(input.get("model") or "")
        object_id = input.get("object_id")
        nested = input.get("nested") or []
        if not isinstance(nested, list):
            nested = []

        extractor = DetailContractExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        try:
            contract = extractor.extract(
                app,
                model,
                user=user,
                object_id=object_id,
                nested=nested,
            )
        except GraphQLError as exc:
            return {"ok": False, "reason": str(exc), "contract": None}

        model_readable = bool(
            (contract.get("permissions", {}) if isinstance(contract, dict) else {}).get(
                "model_readable", False
            )
        )
        if not model_readable:
            return {
                "ok": False,
                "reason": "Access denied",
                "contract": contract,
            }
        return {"ok": True, "reason": None, "contract": contract}

    def resolve_filterSchema(self, info, app: str, model: str) -> list[dict]:
        """Resolve available filters for a model."""
        user = getattr(info.context, "user", None)
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        try:
            model_cls = apps.get_model(app, model)
            if not _user_can_discover_model(model_cls, user):
                return []
            return extractor.extract_model_filters(model_cls, user=user)
        except LookupError:
            return []

    def resolve_fieldFilterSchema(
        self, info, app: str, model: str, field: str
    ) -> Optional[dict]:
        """Resolve metadata for a specific filter field."""
        user = getattr(info.context, "user", None)
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        try:
            model_cls = apps.get_model(app, model)
            if not _user_can_discover_model(model_cls, user):
                return None
            return extractor.extract_filter_field(model_cls, field, user=user)
        except LookupError:
            return None

    def resolve_metadataDeployVersion(self, info, key: Optional[str] = None) -> str:
        from .deploy_version import get_deploy_version

        return get_deploy_version(key)

    def resolve_frontendRouteAccess(self, info) -> dict:
        from .deploy_version import get_deploy_version

        user = getattr(info.context, "user", None)
        return {
            "version": get_deploy_version("frontend_route_access"),
            "rules": frontend_route_access_registry.snapshot_for_user(user),
        }

    def resolve_availableModels(self, info, app: Optional[str] = None) -> list[dict]:
        """
        Resolve list of available models.

        Args:
            info: GraphQL resolve info.
            app: Optional app filter.

        Returns:
            List of model info dicts.
        """
        results = []
        for model in apps.get_models():
            if app and model._meta.app_label != app:
                continue
            if model._meta.app_label in ("admin", "auth", "contenttypes", "sessions"):
                continue
            if not _user_can_discover_model(model, getattr(info.context, "user", None)):
                continue
            results.append(
                {
                    "app": model._meta.app_label,
                    "model": model.__name__,
                    "verbose_name": str(model._meta.verbose_name),
                    "verbose_name_plural": str(model._meta.verbose_name_plural),
                }
            )
        return results

    def resolve_appSchemas(self, info, app: str) -> list[dict]:
        """
        Resolve schemas for all models in an app.

        Args:
            info: GraphQL resolve info.
            app: Django app label.

        Returns:
            List of model schemas.
        """
        user = getattr(info.context, "user", None)
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        schemas = []
        for model in apps.get_app_config(app).get_models():
            if not _user_can_discover_model(model, user):
                continue
            try:
                schemas.append(extractor.extract(app, model.__name__, user=user))
            except Exception as e:
                logger.warning(
                    f"Error extracting schema for {app}.{model.__name__}: {e}"
                )
        return schemas
