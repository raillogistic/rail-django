"""
Generator for unified relation input types.
"""

from typing import Type, Optional, Dict
import graphene
from django.db import models
from .relation_config import FieldRelationConfig


class RelationInputTypeGenerator:
    """Generates unified relation input types (connect/create/update/etc)."""

    def __init__(self, type_generator):
        self.type_generator = type_generator
        self._registry: Dict[str, Type[graphene.InputObjectType]] = {}

    def generate_relation_input_type(
        self,
        related_model: Type[models.Model],
        relation_type: str,  # "fk", "o2o", "m2m", "reverse"
        parent_model: Optional[Type[models.Model]] = None,
        depth: int = 0,
        config: Optional[FieldRelationConfig] = None,
        remote_field_name: Optional[str] = None,
    ) -> Type[graphene.InputObjectType]:
        """
        Generates a unified input type for a relationship.

        Example for FK:
        class AuthorRelationInput(InputObjectType):
            connect = ID()
            create = CreateAuthorInput()
            update = UpdateAuthorInput()
        """
        # Create unique cache key
        cache_key = f"{related_model._meta.label_lower}_{relation_type}_Input"
        if parent_model:
            cache_key += f"_from_{parent_model._meta.model_name}"
        if remote_field_name:
            cache_key += f"_exclude_{remote_field_name}"
        
        cache_key += f"_depth{depth}"

        if cache_key in self._registry:
            return self._registry[cache_key]

        fields = {}

        # 1. Connect (ID) - Always available for all relation types
        is_list = relation_type in ("m2m", "reverse")

        connect_enabled = config.connect.enabled if config else True
        if connect_enabled:
            if is_list:
                fields["connect"] = graphene.InputField(graphene.List(graphene.ID))
            else:
                fields["connect"] = graphene.InputField(graphene.ID)

        # 2. Disconnect (ID) - Only for M2M/Reverse
        disconnect_enabled = config.disconnect.enabled if config else True
        if is_list and disconnect_enabled:
            fields["disconnect"] = graphene.InputField(graphene.List(graphene.ID))

        # 3. Set (ID) - Only for M2M/Reverse (Replaces all)
        set_enabled = config.set.enabled if config else True
        if is_list and set_enabled:
            fields["set"] = graphene.InputField(graphene.List(graphene.ID))

        style = getattr(config, "style", "unified") if config else "unified"

        # 4. Create (Input)
        create_enabled = config.create.enabled if config else True
        if str(style).lower() == "id_only":
            create_enabled = False
        max_depth = getattr(self.type_generator.mutation_settings, "relation_max_nesting_depth", 3)

        if depth < max_depth and create_enabled:
            # Pass remote_field_name as excluded field to generate_input_type
            exclude_fields = [remote_field_name] if remote_field_name else None

            # We need the Input type for the related model.
            # We ask TypeGenerator for it.
            # Note: We use 'create' mutation type for the nested object.
            nested_create_input = self.type_generator.generate_input_type(
                related_model,
                mutation_type="create",
                partial=False,
                include_reverse_relations=False,  # Prevent explosion
                exclude_fields=exclude_fields,
                depth=depth + 1
            )

            if is_list:
                fields["create"] = graphene.InputField(graphene.List(nested_create_input))
            else:
                fields["create"] = graphene.InputField(nested_create_input)

        # 5. Update (Input)
        update_enabled = config.update.enabled if config else True
        if str(style).lower() == "id_only":
            update_enabled = False
        if depth < max_depth and update_enabled:
            # For update, we usually need the ID to identify WHICH object to update
            # inside the nested payload.
            nested_update_input = self.type_generator.generate_input_type(
                related_model,
                mutation_type="update",
                partial=True,
                include_reverse_relations=False,
                depth=depth + 1
            )

            if is_list:
                fields["update"] = graphene.InputField(graphene.List(nested_update_input))
            else:
                fields["update"] = graphene.InputField(nested_update_input)

        # Create the InputObjectType dynamically
        type_name = f"{related_model.__name__}RelationInput"
        if parent_model:
            type_name = f"{parent_model.__name__}{related_model.__name__}RelationInput"
        if remote_field_name:
            type_name += f"Exclude{remote_field_name.title()}"
        
        if depth > 0:
            type_name += f"Level{depth}"

        relation_input = type(
            type_name,
            (graphene.InputObjectType,),
            fields
        )

        self._registry[cache_key] = relation_input
        return relation_input
