"""Mutation metadata extraction methods.

This module provides mixin classes for extracting mutation metadata
from Django models for GraphQL schema generation.
"""

import logging
from typing import Any, Optional

from django.db import models

from ..types import InputFieldMetadata, MutationMetadata
from .mutation_inputs import InputFieldExtractionMixin

logger = logging.getLogger(__name__)


class MutationExtractionMixin(InputFieldExtractionMixin):
    """
    Mixin providing mutation metadata extraction functionality.

    This mixin should be used with BaseMetadataExtractor to provide
    mutation extraction capabilities.
    """

    def extract_mutations_metadata(
        self, model: type[models.Model], user=None
    ) -> list[MutationMetadata]:
        """
        Extract mutation metadata for a Django model.

        Args:
            model: Django model class.
            user: Optional user for permission filtering.

        Returns:
            List of MutationMetadata objects.
        """
        try:
            from ....config_proxy import get_mutation_generator_settings
            from ....generators.mutations import MutationGenerator
            from ....generators.types import TypeGenerator

            mutations = []

            type_generator = TypeGenerator(schema_name=self.schema_name)
            mutation_settings = get_mutation_generator_settings(self.schema_name)
            mutation_generator = MutationGenerator(
                type_generator=type_generator,
                settings=mutation_settings,
                schema_name=self.schema_name,
            )

            if mutation_settings.enable_create:
                create_mutation = self._extract_create_mutation_metadata(model)
                if create_mutation:
                    mutations.append(create_mutation)

            if mutation_settings.enable_update:
                update_mutation = self._extract_update_mutation_metadata(model)
                if update_mutation:
                    mutations.append(update_mutation)

            if mutation_settings.enable_delete:
                delete_mutation = self._extract_delete_mutation_metadata(model)
                if delete_mutation:
                    mutations.append(delete_mutation)

            if mutation_settings.enable_bulk_operations:
                bulk_mutations = self._extract_bulk_mutations_metadata(model)
                mutations.extend(bulk_mutations)

            if mutation_settings.enable_method_mutations:
                method_mutations = self._extract_method_mutations_metadata(
                    model, user=user
                )
                mutations.extend(method_mutations)

            return mutations

        except Exception as e:
            logger.error(f"Error extracting mutations for {model.__name__}: {e}")
            return []

    def _extract_create_mutation_metadata(
        self, model: type[models.Model]
    ) -> Optional[MutationMetadata]:
        """Extract metadata for create mutation."""
        try:
            model_name = model.__name__
            input_fields = self._extract_input_fields_from_model(model, "create")

            return MutationMetadata(
                name=f"create_{model_name.lower()}",
                description=f"Create a new {model_name} instance",
                input_fields=input_fields,
                return_type=f"{model_name}Type",
                requires_authentication=True,
                required_permissions=[
                    f"{model._meta.app_label}.add_{model._meta.model_name}"
                ],
                mutation_type="create",
                model_name=model_name,
                success_message=f"{model_name} created successfully",
                form_config={
                    "title": f"Create {model_name}",
                    "submit_text": "Create",
                    "cancel_text": "Cancel",
                },
            )
        except Exception as e:
            logger.error(f"Error extracting create mutation metadata: {e}")
            return None

    def _extract_update_mutation_metadata(
        self, model: type[models.Model]
    ) -> Optional[MutationMetadata]:
        """Extract metadata for update mutation."""
        try:
            model_name = model.__name__
            input_fields = self._extract_input_fields_from_model(model, "update")

            id_field = InputFieldMetadata(
                name="id",
                field_type="ID",
                required=True,
                description=f"ID of the {model_name} to update",
                widget_type="hidden",
            )
            input_fields.insert(0, id_field)

            return MutationMetadata(
                name=f"update_{model_name.lower()}",
                description=f"Update an existing {model_name} instance",
                input_fields=input_fields,
                return_type=f"{model_name}Type",
                requires_authentication=True,
                required_permissions=[f"change_{model._meta.model_name}"],
                mutation_type="update",
                model_name=model_name,
                success_message=f"{model_name} updated successfully",
                form_config={
                    "title": f"Update {model_name}",
                    "submit_text": "Update",
                    "cancel_text": "Cancel",
                },
            )
        except Exception as e:
            logger.error(f"Error extracting update mutation metadata: {e}")
            return None

    def _extract_delete_mutation_metadata(
        self, model: type[models.Model]
    ) -> Optional[MutationMetadata]:
        """Extract metadata for delete mutation."""
        try:
            model_name = model.__name__

            id_field = InputFieldMetadata(
                name="id",
                field_type="ID",
                required=True,
                description=f"ID of the {model_name} to delete",
                widget_type="hidden",
            )

            return MutationMetadata(
                name=f"delete_{model_name.lower()}",
                description=f"Delete a {model_name} instance",
                input_fields=[id_field],
                return_type="Boolean",
                requires_authentication=True,
                required_permissions=[f"delete_{model._meta.model_name}"],
                mutation_type="delete",
                model_name=model_name,
                success_message=f"{model_name} deleted successfully",
                form_config={
                    "title": f"Delete {model_name}",
                    "submit_text": "Delete",
                    "cancel_text": "Cancel",
                    "confirmation_required": True,
                    "confirmation_message": f"Are you sure you want to delete this {model_name}?",
                },
            )
        except Exception as e:
            logger.error(f"Error extracting delete mutation metadata: {e}")
            return None

    def _extract_bulk_mutations_metadata(
        self, model: type[models.Model]
    ) -> list[MutationMetadata]:
        """Extract metadata for bulk mutations."""
        mutations = []
        model_name = model.__name__

        try:
            bulk_create = MutationMetadata(
                name=f"bulk_create_{model_name.lower()}",
                description=f"Create multiple {model_name} instances",
                input_fields=[
                    InputFieldMetadata(
                        name="objects",
                        field_type="List",
                        required=True,
                        description=f"List of {model_name} objects to create",
                        multiple=True,
                    )
                ],
                return_type=f"List[{model_name}Type]",
                requires_authentication=True,
                required_permissions=[f"add_{model._meta.model_name}"],
                mutation_type="bulk_create",
                model_name=model_name,
                success_message=f"Multiple {model_name} instances created",
            )
            mutations.append(bulk_create)

            bulk_update = MutationMetadata(
                name=f"bulk_update_{model_name.lower()}",
                description=f"Update multiple {model_name} instances",
                input_fields=[
                    InputFieldMetadata(
                        name="objects",
                        field_type="List",
                        required=True,
                        description=f"List of {model_name} objects to update",
                        multiple=True,
                    )
                ],
                return_type=f"List[{model_name}Type]",
                requires_authentication=True,
                required_permissions=[f"change_{model._meta.model_name}"],
                mutation_type="bulk_update",
                model_name=model_name,
                success_message=f"Multiple {model_name} instances updated",
            )
            mutations.append(bulk_update)

            bulk_delete = MutationMetadata(
                name=f"bulk_delete_{model_name.lower()}",
                description=f"Delete multiple {model_name} instances",
                input_fields=[
                    InputFieldMetadata(
                        name="ids",
                        field_type="List[ID]",
                        required=True,
                        description=f"List of {model_name} IDs to delete",
                        multiple=True,
                    )
                ],
                return_type="Boolean",
                requires_authentication=True,
                required_permissions=[f"delete_{model._meta.model_name}"],
                mutation_type="bulk_delete",
                model_name=model_name,
                success_message=f"Multiple {model_name} instances deleted",
            )
            mutations.append(bulk_delete)

        except Exception as e:
            logger.error(f"Error extracting bulk mutations metadata: {e}")

        return mutations

    def _extract_method_mutations_metadata(
        self, model: type[models.Model], user=None
    ) -> list[MutationMetadata]:
        """Extract metadata for method-based mutations."""
        mutations = []

        try:
            from ....generators.introspector import ModelIntrospector

            introspector = ModelIntrospector.for_model(model)
            model_methods = introspector.get_model_methods()

            for method_name, method_info in model_methods.items():
                if method_info.is_mutation and not method_info.is_private:
                    method_mutation = self._extract_method_mutation_metadata(
                        model, method_name, method_info, user=user
                    )
                    if method_mutation:
                        mutations.append(method_mutation)

        except Exception as e:
            logger.error(f"Error extracting method mutations metadata: {e}")

        return mutations

    def _extract_method_mutation_metadata(
        self, model: type[models.Model], method_name: str, method_info, user=None
    ) -> Optional[MutationMetadata]:
        """Extract metadata for a specific method mutation."""
        try:
            model_name = model.__name__
            method = getattr(model, method_name)

            input_fields = self._extract_input_fields_from_method(method)
            input_type_name = None

            description = getattr(method, "_mutation_description", method.__doc__)
            custom_name = getattr(method, "_custom_mutation_name", None)
            requires_permissions = getattr(method, "_requires_permissions", None)
            if requires_permissions is None:
                legacy = getattr(method, "_requires_permission", None)
                requires_permissions = [legacy] if legacy else []
            action_meta = getattr(method, "_action_ui", None)
            action_kind = getattr(method, "_action_kind", None)

            mutation_name = custom_name or f"{model_name.lower()}_{method_name}"
            if input_fields:
                input_type_name = (
                    getattr(method, "_mutation_input_type", None).__name__
                    if getattr(method, "_mutation_input_type", None)
                    else f"{model_name}{method_name.title()}Input"
                )
            action_payload = None
            if action_meta:
                action_payload = self._sanitize_action_payload({
                    **action_meta,
                    "kind": action_kind or action_meta.get("mode"),
                    "label": action_meta.get("title") or method_name.replace("_", " ").title(),
                })
                if action_kind == "confirm":
                    input_fields = []
                    input_type_name = None

            if user and requires_permissions:
                missing = [
                    perm for perm in requires_permissions if not user.has_perm(perm)
                ]
                if missing:
                    return None

            return MutationMetadata(
                name=mutation_name,
                method_name=method_name,
                description=description or f"Execute {method_name} on {model_name}",
                input_fields=input_fields,
                return_type="JSONString",
                input_type=input_type_name,
                requires_authentication=True,
                required_permissions=requires_permissions or [],
                mutation_type="custom",
                model_name=model_name,
                success_message=f"{method_name} executed successfully",
                action=action_payload,
            )

        except Exception as e:
            logger.error(f"Error extracting method mutation metadata: {e}")
            return None


__all__ = ["MutationExtractionMixin"]
