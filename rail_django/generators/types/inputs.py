"""
Input type generation helpers.
"""

from typing import Dict, Optional, Type, List

import graphene
from django.db import models

from ..introspector import ModelIntrospector, FieldInfo


def generate_input_type(
    self,
    model: type[models.Model],
    mutation_type: str = "create",
    partial: bool = False,
    include_reverse_relations: bool = True,
    exclude_fields: Optional[List[str]] = None,
    depth: int = 0,
) -> type[graphene.InputObjectType]:
    """
    Generates a GraphQL input type for mutations.
    Handles unified nested inputs, validation, and reverse relationships.
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

    exclude_tuple = tuple(sorted(exclude_fields)) if exclude_fields else ()
    cache_key = (model, partial, mutation_type, include_reverse_relations, exclude_tuple, depth)
    if cache_key in self._input_type_registry:
        return self._input_type_registry[cache_key]

    introspector = ModelIntrospector.for_model(model)
    fields = introspector.get_model_fields()
    relationships = introspector.get_model_relationships()

    # Create input fields
    input_fields = {}

    for field_name, field_info in fields.items():
        if exclude_fields and field_name in exclude_fields:
            continue
            
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

    # Add forward relationship fields with UNIFIED input generation
    for field_name, rel_info in relationships.items():
        if exclude_fields and field_name in exclude_fields:
            continue
            
        if not self._should_include_field(model, field_name, for_input=True):
            continue
        
        # Use RelationInputTypeGenerator
        relation_type = "fk"
        if rel_info.relationship_type == "OneToOneField":
            relation_type = "o2o"
        elif rel_info.relationship_type == "ManyToManyField":
            relation_type = "m2m"
            
        relation_input = self.relation_input_generator.generate_relation_input_type(
            related_model=rel_info.related_model,
            relation_type=relation_type,
            parent_model=model,
            depth=depth
        )
        
        # Determine if required
        is_required = False
        if mutation_type == "create":
             # Should check underlying field requirement
             try:
                 django_field = model._meta.get_field(field_name)
                 if not django_field.null and django_field.default == models.NOT_PROVIDED:
                     is_required = not partial
             except Exception:
                 pass
        
        # M2M is never required in Django (defaults to empty list)
        if rel_info.relationship_type == "ManyToManyField":
            is_required = False

        if is_required:
             input_fields[field_name] = graphene.InputField(graphene.NonNull(relation_input))
        else:
             input_fields[field_name] = graphene.InputField(relation_input)


    # Add reverse relationship fields
    if include_reverse_relations:
        reverse_relations = self._get_reverse_relations(model)
        for field_name, rel_info in reverse_relations.items():
            if exclude_fields and field_name in exclude_fields:
                continue
                
            related_model = (
                rel_info.get("model") if isinstance(rel_info, dict) else rel_info
            )
            if related_model is None:
                continue
            if not self._should_include_field(model, field_name, for_input=True):
                continue
                
            # Check if explicit reverse relation config allows this? 
            # Reusing existing check for now
            if not self._should_include_nested_field(model, field_name):
                continue

            # Extract remote field name to exclude it in the nested input
            remote_field_name = None
            if isinstance(rel_info, dict) and "relation" in rel_info:
                 relation = rel_info["relation"]
                 if hasattr(relation, "field"):
                      remote_field_name = relation.field.name

            relation_input = self.relation_input_generator.generate_relation_input_type(
                related_model=related_model,
                relation_type="reverse",
                parent_model=model,
                depth=depth,
                remote_field_name=remote_field_name
            )
            
            input_fields[field_name] = graphene.InputField(relation_input)

    # Create the input type class
    prefix = ""
    if mutation_type == "update" and partial:
        prefix = "Update"
    elif mutation_type == "create":
        prefix = "Create"
    
    # Suffix for exclusion uniqueness
    suffix = ""
    if exclude_fields:
        suffix = "Exclude" + "".join(sorted([f.title() for f in exclude_fields]))
    
    # Append depth to prevent name collisions
    if depth > 0:
        suffix += f"Level{depth}"
        
    class_name = f"{prefix}{model.__name__}{suffix}Input"
    if not prefix and not suffix:
         class_name = f"{model.__name__}Input"
        
    input_type = type(
        class_name,
        (graphene.InputObjectType,),
        {
            "__doc__": f"Input type for creating/updating {model.__name__} instances with unified nested relationships.",
            **input_fields,
        },
    )

    # Store in registry
    self._input_type_registry[cache_key] = input_type
    return input_type
