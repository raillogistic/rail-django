"""
Input type generation helpers.
"""

from typing import Dict, Optional, Type

import graphene
from django.db import models

from ..introspector import ModelIntrospector, FieldInfo


def generate_input_type(
    self,
    model: type[models.Model],
    mutation_type: str = "create",
    partial: bool = False,
    include_reverse_relations: bool = True,
) -> type[graphene.InputObjectType]:
    """
    Generates a GraphQL input type for mutations.
    Handles nested inputs, validation, and reverse relationships.
    """
    # Backward-compatible argument handling
    if isinstance(mutation_type, bool) and isinstance(partial, str):
        mutation_type, partial = partial, mutation_type
    elif isinstance(mutation_type, bool) and isinstance(partial, bool):
        partial = mutation_type
        mutation_type = "create"
    if isinstance(partial, str):
        mutation_type = partial
        partial = False

    cache_key = (model, partial, mutation_type, include_reverse_relations)
    if cache_key in self._input_type_registry:
        return self._input_type_registry[cache_key]

    introspector = ModelIntrospector.for_model(model)
    fields = introspector.get_model_fields()
    relationships = introspector.get_model_relationships()

    # Create input fields
    input_fields = {}

    for field_name, field_info in fields.items():
        if not self._should_include_field(model, field_name, for_input=True):
            continue

        if field_name == "id":
            # Keep ID only for update mutations; input ID is optional because the top-level id arg is required.
            if mutation_type != "update":
                continue

            field_type = (
                self._get_input_field_type(field_info.field_type) or graphene.ID
            )
            input_fields[field_name] = graphene.InputField(
                field_type, description=field_info.help_text
            )
            continue

        # Get field type, fallback to handle_custom_fields if not in mapping
        field_type = self._get_input_field_type(field_info.field_type)
        if not field_type:
            # Handle custom fields that aren't in FIELD_TYPE_MAP
            field_type = self.handle_custom_fields(field_info.field_type)

        # If this is a CharField/TextField with choices, we previously generated an Enum.
        # However, to ensure consistency with metadata values (which use raw values like "km")
        # and avoid Enum Name mismatches ("KM"), we now force String input for choices
        # by skipping the enum conversion logic here.

        # Determine if field should be required based on mutation type
        if mutation_type == "create":
            is_required = (
                self._should_field_be_required_for_create(
                    field_info, field_name, model
                )
                and not partial
            )
        else:  # update
            # For updates, all non-id fields remain optional to support partial updates
            is_required = self._should_field_be_required_for_update(
                field_name, field_info, model
            )

        # Create the field with proper required handling
        if is_required:
            input_fields[field_name] = graphene.InputField(
                graphene.NonNull(field_type), description=field_info.help_text
            )
        else:
            input_fields[field_name] = field_type(description=field_info.help_text)

    # Add forward relationship fields with automatic dual field generation
    for field_name, rel_info in relationships.items():
        if not self._should_include_field(model, field_name, for_input=True):
            continue

        # Get the actual Django field to check its requirements
        django_field = model._meta.get_field(field_name)

        # Create a FieldInfo object for the relationship field to check requirements
        rel_field_info = FieldInfo(            field_type=type(django_field),
            is_required=not django_field.null,
            default_value=django_field.default
            if django_field.default is not models.NOT_PROVIDED
            else None,
            help_text=str(django_field.help_text),
            has_auto_now=getattr(django_field, "auto_now", False),
            has_auto_now_add=getattr(django_field, "auto_now_add", False),
            blank=getattr(django_field, "blank", False),
            has_default=django_field.default is not models.NOT_PROVIDED,
        )

        # Apply field requirement logic to relationship fields
        # For ManyToMany fields, use blank attribute instead of null
        if rel_info.relationship_type == "ManyToManyField":
            is_required = False
        else:
            if mutation_type == "create":
                is_required = (
                    self._should_field_be_required_for_create(
                        rel_field_info, field_name, model
                    )
                    and not partial
                )
            else:  # update
                is_required = self._should_field_be_required_for_update(
                    field_name, rel_field_info, model
                )

        # Always generate both nested and direct ID fields for all relationships
        if rel_info.relationship_type in ("ForeignKey", "OneToOneField"):
            # Check if this field is part of a mandatory dual field pair
            mandatory_fields = self._get_mandatory_fields(model)
            is_mandatory_dual_field = field_name in mandatory_fields

            # 1. Add direct ID field: <field_name>
            # For mandatory dual fields, make the direct field optional in schema
            # but enforce requirement in mutation logic
            if is_required and is_mandatory_dual_field:
                # Make mandatory dual fields optional in GraphQL schema
                input_fields[field_name] = graphene.ID()
            elif is_required:
                # Regular required fields remain NonNull
                input_fields[field_name] = graphene.InputField(
                    graphene.NonNull(graphene.ID)
                )
            else:
                # Optional fields remain optional
                input_fields[field_name] = graphene.ID()

            # 2. Add nested field: nested_<field_name>
            if self._should_include_nested_field(model, field_name):
                nested_field_name = f"nested_{field_name}"
                nested_input_type = self._get_or_create_nested_input_type(
                    rel_info.related_model, mutation_type, exclude_parent_field=model
                )
                input_fields[nested_field_name] = graphene.InputField(
                    nested_input_type
                )

        elif rel_info.relationship_type == "ManyToManyField":
            # 1. Add direct ID list field: <field_name>
            input_fields[field_name] = graphene.JSONString()

            # 2. Add nested field: nested_<field_name>
            if self._should_include_nested_field(model, field_name):
                nested_field_name = f"nested_{field_name}"
                nested_input_type = self._get_or_create_nested_input_type(
                    rel_info.related_model, mutation_type, exclude_parent_field=model
                )
                input_fields[nested_field_name] = graphene.InputField(
                    graphene.List(nested_input_type)
                )

    # Add reverse relationship fields with dual field generation for nested operations (e.g., comments for Post)
    if include_reverse_relations:
        reverse_relations = self._get_reverse_relations(model)
        for field_name, rel_info in reverse_relations.items():
            related_model = (
                rel_info.get("model") if isinstance(rel_info, dict) else rel_info
            )
            if related_model is None:
                continue
            if not self._should_include_field(model, field_name, for_input=True):
                continue

            # Always generate both direct ID list and nested fields for reverse relations
            # 1. Add direct ID list field: <field_name>
            input_fields[field_name] = graphene.List(graphene.ID)

            # 2. Add nested field: nested_<field_name>
            if self._should_include_nested_field(model, field_name):
                nested_field_name = f"nested_{field_name}"
                # Use the appropriate mutation type for nested input generation
                nested_mutation_type = (
                    "create" if mutation_type == "create" else "update"
                )
                nested_input_type = self._get_or_create_nested_input_type(
                    related_model, nested_mutation_type, exclude_parent_field=model
                )
                input_fields[nested_field_name] = graphene.List(nested_input_type)

    # Create the input type class
    # Generate different class names for different mutation types
    if mutation_type == "update" and partial:
        class_name = f"Update{model.__name__}Input"
    elif mutation_type == "create":
        class_name = f"Create{model.__name__}Input"
    else:
        class_name = f"{model.__name__}Input"
    input_type = type(
        class_name,
        (graphene.InputObjectType,),
        {
            "__doc__": f"Input type for creating/updating {model.__name__} instances with nested relationships.",
            **input_fields,
        },
    )

    # Store in registry with comprehensive cache key
    cache_key = (model, partial, mutation_type, include_reverse_relations)
    self._input_type_registry[cache_key] = input_type
    return input_type


def _get_or_create_nested_input_type(
    self,
    model: type[models.Model],
    mutation_type: str = "create",
    exclude_parent_field: Optional[type[models.Model]] = None,
) -> type[graphene.InputObjectType]:
    """
    Get or create a nested input type for a model, avoiding circular references.
    """
    # Create a simplified input type to avoid infinite recursion
    # Include exclude_parent_field in cache key to ensure different types for different parents
    exclude_suffix = (
        f"_exclude_{exclude_parent_field.__name__}" if exclude_parent_field else ""
    )
    cache_key = (
        f"{model.__name__}Nested{mutation_type.title()}Input{exclude_suffix}"
    )

    if cache_key in self._input_type_registry:
        return self._input_type_registry[cache_key]

    introspector = ModelIntrospector.for_model(model)
    fields = introspector.get_model_fields()
    relationships = introspector.get_model_relationships()

    input_fields = {}

    # Add regular fields
    for field_name, field_info in fields.items():
        if not self._should_include_field(model, field_name, for_input=True):
            continue

        # Skip id field for create mutations
        if mutation_type == "create" and field_name == "id":
            continue

        # Determine input type, with Enum support for choice fields
        field_type = self._get_input_field_type(field_info.field_type)
        if not field_type:
            field_type = self.handle_custom_fields(field_info.field_type)

        # If CharField/TextField has choices, we skip Enum generation to ensure
        # consistency with raw values (e.g. "km") expected by the frontend.

        # For nested inputs, make most fields optional to allow partial data
        is_required = False
        if mutation_type == "create":
            is_required = self._should_field_be_required_for_create(
                field_info, field_name, model
            )

        input_fields[field_name] = field_type(
            required=is_required, description=field_info.help_text
        )

    # Add only essential relationship fields (avoid deep nesting)
    for field_name, rel_info in relationships.items():
        if not self._should_include_field(model, field_name, for_input=True):
            continue

        # Skip the parent field to prevent circular references
        if exclude_parent_field and rel_info.related_model == exclude_parent_field:
            continue

        # For nested inputs, use only ID references for relationships
        if rel_info.relationship_type in ("ForeignKey", "OneToOneField"):
            input_fields[field_name] = graphene.ID(required=False)
        elif rel_info.relationship_type == "ManyToManyField":
            input_fields[field_name] = graphene.List(graphene.ID)

    # Create the nested input type
    nested_input_type = type(
        cache_key,
        (graphene.InputObjectType,),
        {
            "__doc__": f"Nested input type for {model.__name__} in {mutation_type} operations.",
            **input_fields,
        },
    )

    self._input_type_registry[cache_key] = nested_input_type
    return nested_input_type
