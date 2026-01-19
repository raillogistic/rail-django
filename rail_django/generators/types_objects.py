"""
Object type generation helpers.
"""

from typing import Any, Dict, List, Optional, Type

import graphene
from django.db import models
from graphene_django import DjangoObjectType

from ..utils.history import serialize_history_changes
from .inheritance import inheritance_handler
from .introspector import ModelIntrospector

try:
    import graphql
except Exception:
    graphql = None

try:
    from promise import Promise
except Exception:
    Promise = None

_GRAPHQL_MAJOR = 0
if graphql is not None:
    try:
        _GRAPHQL_MAJOR = int(str(graphql.__version__).split(".")[0])
    except Exception:
        _GRAPHQL_MAJOR = 0


def _resolve_promise(value):
    if _GRAPHQL_MAJOR < 3:
        return value
    if Promise is None:
        return value
    if isinstance(value, Promise):
        try:
            return value.get()
        except Exception:
            return value
    return value


def generate_object_type(self, model: type[models.Model]) -> type[DjangoObjectType]:
    """
    Generates a GraphQL object type for a Django model.
    Handles relationships and custom field mappings.
    """
    if model in self._type_registry:
        return self._type_registry[model]

    introspector = ModelIntrospector.for_model(model)
    fields = introspector.get_model_fields()
    relationships = introspector.get_model_relationships()
    maskable_fields = self._get_maskable_fields(model)
    apply_tenant_scope = self._apply_tenant_scope

    # Get excluded fields for this model
    exclude_fields = self._get_excluded_fields(model)

    # Create the Meta class for the DjangoObjectType
    meta_attrs = {
        "model": model,
        "exclude_fields": exclude_fields,
        "convert_choices_to_enum": False,
        "interfaces": (graphene.relay.Node,)
        if self.settings.generate_filters
        else (),
    }
    meta_class = type("Meta", (), meta_attrs)

    # Create the object type class
    class_name = f"{model.__name__}Type"
    type_attrs = {
        "Meta": meta_class,
        "__doc__": f"GraphQL type for the {model.__name__} model.",
    }

    # Add pk field that resolves to the model's primary key
    type_attrs["pk"] = graphene.ID(description="Primary key of the model")
    type_attrs["resolve_pk"] = lambda self, info: getattr(self, self._meta.pk.name)

    def desc_resolver():
        def desc_resolver(self, info):
            desc = getattr(self, "desc", None) or self.__str__() or ""
            return desc

        return desc_resolver

    # add desc field for desc
    type_attrs["desc"] = graphene.String(description="Description of the object")
    type_attrs["resolve_desc"] = desc_resolver()
    # Add custom field resolvers
    is_historical_model = self._is_historical_model(model)

    if is_historical_model:
        type_attrs["instance_id"] = graphene.ID(
            description="Identifiant de l'objet original"
        )

        def resolve_instance_id(self, info):
            raw = getattr(self, "instance_id", None)
            if raw is None:
                try:
                    instance = getattr(self, "instance", None)
                    if instance is not None:
                        raw = getattr(instance, instance._meta.pk.name, None)
                except Exception:
                    raw = None
            if raw is None:
                raw = getattr(self, "id", None)
            return str(raw) if raw is not None else None

        type_attrs["resolve_instance_id"] = resolve_instance_id
        type_attrs["history_changes"] = graphene.JSONString(
            description="Liste structurÇ¸e des modifications effectuÇ¸es lors de cette rÇ¸vision"
        )

        def resolve_history_changes(self, info):
            return serialize_history_changes(self)

        type_attrs["resolve_history_changes"] = resolve_history_changes

    for field_name, field_info in fields.items():
        if not self._should_include_field(model, field_name):
            continue
        if is_historical_model and field_name == "id":
            type_attrs[field_name] = graphene.ID(
                description=field_info.help_text or "Identifiant de l'objet"
            )

            def make_history_id_resolver():
                def resolver(self, info):
                    value = getattr(self, "id", None)
                    return str(value) if value is not None else None

                return resolver

            type_attrs[f"resolve_{field_name}"] = make_history_id_resolver()
            continue
        if field_name in maskable_fields:
            try:
                django_field = model._meta.get_field(field_name)
                graphql_type = self.FIELD_TYPE_MAP.get(
                    type(django_field), graphene.String
                )
                type_attrs[field_name] = graphene.Field(graphql_type)
            except Exception:
                pass
        resolver_name = f"resolve_{field_name}"
        if hasattr(self, resolver_name):
            type_attrs[resolver_name] = getattr(self, resolver_name)

        # NEW: Check for choices and add _desc field
        try:
            django_field = model._meta.get_field(field_name)
            if hasattr(django_field, "choices") and django_field.choices:
                # Force String type to avoid Graphene Enum conversion (which returns names like "KM" instead of values "km")
                # We want the raw value for the form to work correctly.
                type_attrs[field_name] = graphene.String(
                    description=field_info.help_text
                )

                desc_field_name = f"{field_name}_desc"
                type_attrs[desc_field_name] = graphene.String(
                    description=f"Display label for {field_name}"
                )

                # Create resolver closure
                def make_desc_resolver(fname):
                    def resolver(self, info):
                        # Ensure the method exists (Django adds it for fields with choices)
                        display_method = getattr(self, f"get_{fname}_display", None)
                        if display_method:
                            return display_method()
                        return getattr(self, fname)

                    return resolver

                type_attrs[f"resolve_{desc_field_name}"] = make_desc_resolver(
                    field_name
                )
        except Exception:
            pass

    # Override ManyToMany fields to use direct lists instead of connections
    for field_name, rel_info in relationships.items():
        if not self._should_include_field(model, field_name):
            continue

        if rel_info.relationship_type == "ManyToManyField":
            # Get the related model
            related_model = rel_info.related_model

            # Use proper lazy type resolution to avoid recursion
            def make_lazy_type(model_ref):
                def lazy_type():
                    # Check if type already exists to avoid infinite recursion
                    if model_ref in self._type_registry:
                        return self._type_registry[model_ref]
                    return self.generate_object_type(model_ref)

                return lazy_type

            # Override the field as a direct list with filter arguments
            type_attrs[field_name] = graphene.List(
                make_lazy_type(related_model),
                filters=graphene.Argument(graphene.JSONString),
                description=f"Related {related_model.__name__} objects",
            )

            # Add count field for ManyToMany relation
            count_field_name = f"{field_name}_count"
            type_attrs[count_field_name] = graphene.Int(
                description=f"Count of related {related_model.__name__} objects"
            )

            # Add resolver that handles different relationship types with filtering
            def make_resolver(field_name, rel_info, related_model):
                def resolver(self, info, filters=None):
                    # Optimization: Use prefetch cache if available and no filters
                    if (
                        not filters
                        and hasattr(self, "_prefetched_objects_cache")
                        and field_name in self._prefetched_objects_cache
                    ):
                        return self._prefetched_objects_cache[field_name]

                    related_obj = getattr(self, field_name)
                    # For OneToOne fields, return the single object or None
                    if rel_info.relationship_type == "OneToOneField":
                        return related_obj
                    # For ForeignKey and ManyToMany, return queryset with optional filtering
                    queryset = related_obj.all()
                    queryset = apply_tenant_scope(
                        queryset, info, related_model, operation="read"
                    )

                    # Apply filters if provided
                    if filters:
                        from .filter_inputs import AdvancedFilterGenerator

                        filter_generator = AdvancedFilterGenerator()
                        filter_set_class = filter_generator.generate_filter_set(
                            related_model
                        )
                        filter_set = filter_set_class(filters, queryset=queryset)
                        queryset = filter_set.qs

                    return queryset

                return resolver

            # Add count resolver for ManyToMany relation
            def make_count_resolver(field_name, related_model):
                def count_resolver(self, info):
                    related_obj = getattr(self, field_name)
                    queryset = related_obj.all()
                    queryset = apply_tenant_scope(
                        queryset, info, related_model, operation="read"
                    )
                    return queryset.count()

                return count_resolver

            # Add parameterized total count resolver with filters
            type_attrs[f"resolve_{field_name}"] = make_resolver(
                field_name, rel_info, related_model
            )
            type_attrs[f"resolve_{count_field_name}"] = make_count_resolver(
                field_name, related_model
            )

    # Add custom resolvers for ALL reverse relationships to return direct model lists
    # instead of relay connections (including Django's default _set relationships)
    reverse_relations = self._get_reverse_relations(model)
    for accessor_name, rel_info in reverse_relations.items():
        related_model = rel_info.get("model")
        relation = rel_info.get("relation")
        if related_model is None:
            continue
        if not self._should_include_field(model, accessor_name):
            continue
        query_optimizer = self.query_optimizer
        get_relation_dataloader = self._get_relation_dataloader

        # Use proper lazy type resolution to avoid recursion
        # Create a closure that captures the related_model
        def make_lazy_type(model_ref):
            def lazy_type():
                # Check if type already exists to avoid infinite recursion
                if model_ref in self._type_registry:
                    return self._type_registry[model_ref]
                return self.generate_object_type(model_ref)

            return lazy_type

        # Check if this is a OneToOne reverse relationship
        is_one_to_one_reverse = False
        if relation is not None:
            try:
                from django.db.models.fields.reverse_related import OneToOneRel

                is_one_to_one_reverse = isinstance(relation, OneToOneRel)
            except Exception:
                is_one_to_one_reverse = False

        # Add the field - single object for OneToOne, list for others
        if is_one_to_one_reverse:
            type_attrs[accessor_name] = graphene.Field(
                make_lazy_type(related_model),
                description=f"Related {related_model.__name__} object",
            )
        else:
            type_attrs[accessor_name] = graphene.List(
                make_lazy_type(related_model),
                filters=graphene.Argument(graphene.JSONString),
                description=f"Related {related_model.__name__} objects",
            )

            # Add count field for reverse ManyToOne relations (e.g., posts_count for User)
            count_field_name = f"{accessor_name}_count"
            type_attrs[count_field_name] = graphene.Int(
                description=f"Count of related {related_model.__name__} objects"
            )

        # Add resolver that handles different relationship types with filtering
        def make_resolver(
            accessor_name,
            is_one_to_one,
            related_model,
            relation,
            query_optimizer,
            get_relation_dataloader,
            apply_tenant_scope,
        ):
            def resolver(self, info, filters=None):
                # Optimization: Use prefetch cache if available and no filters (for lists)
                if (
                    not is_one_to_one
                    and not filters
                    and hasattr(self, "_prefetched_objects_cache")
                    and accessor_name in self._prefetched_objects_cache
                ):
                    return self._prefetched_objects_cache[accessor_name]

                # For OneToOne reverse relationships, handle DoesNotExist exceptions
                if is_one_to_one:
                    try:
                        related_obj = getattr(self, accessor_name)
                        return related_obj
                    except related_model.DoesNotExist:
                        return None
                # For other relationships, return queryset with optional filtering
                related_obj = getattr(self, accessor_name)
                queryset = related_obj.all()
                queryset = apply_tenant_scope(
                    queryset, info, related_model, operation="read"
                )

                if relation is not None and query_optimizer.settings.enable_dataloader:
                    loader = get_relation_dataloader(
                        info.context,
                        related_model,
                        relation,
                        getattr(self, "_state", None),
                    )
                    if loader:
                        parent_id = getattr(self, "pk", None)
                        if parent_id is None:
                            return []
                        return _resolve_promise(loader.load(parent_id))

                # Apply filters if provided
                if filters:
                    from .filters import AdvancedFilterGenerator

                    filter_generator = AdvancedFilterGenerator()
                    filter_set_class = filter_generator.generate_filter_set(
                        related_model
                    )
                    filter_set = filter_set_class(filters, queryset=queryset)
                    queryset = filter_set.qs

                return queryset

            return resolver

        # Add count resolver for reverse ManyToOne relations
        def make_count_resolver(accessor_name, is_one_to_one, related_model):
            def count_resolver(self, info):
                if is_one_to_one:
                    # For OneToOne, return 1 if exists, 0 if not
                    related_obj = getattr(self, accessor_name, None)
                    return 1 if related_obj else 0
                # For ManyToOne reverse relations, count the related objects
                related_obj = getattr(self, accessor_name)
                queryset = related_obj.all()
                queryset = apply_tenant_scope(
                    queryset, info, related_model, operation="read"
                )
                return queryset.count()

            return count_resolver

        type_attrs[f"resolve_{accessor_name}"] = make_resolver(
            accessor_name,
            is_one_to_one_reverse,
            related_model,
            relation,
            query_optimizer,
            get_relation_dataloader,
            apply_tenant_scope,
        )

        # Add count resolver only for non-OneToOne relationships
        if not is_one_to_one_reverse:
            count_field_name = f"{accessor_name}_count"
            type_attrs[f"resolve_{count_field_name}"] = make_count_resolver(
                accessor_name, is_one_to_one_reverse, related_model
            )

    # Add @property methods as GraphQL fields
    properties = introspector.properties
    for prop_name, prop_info in properties.items():
        if not self._should_include_field(model, prop_name):
            continue
        if is_historical_model and prop_name == "instance":
            continue

        # Convert the property's return type to a GraphQL field
        graphql_field = self._get_graphql_type_for_property(prop_info.return_type)
        type_attrs[prop_name] = graphql_field

        # Add resolver that calls the property
        def make_property_resolver(property_name):
            def resolver(self, info):
                return getattr(self, property_name)

            return resolver

        type_attrs[f"resolve_{prop_name}"] = make_property_resolver(prop_name)

    # Create the type class with Meta configuration
    meta_attrs = {
        "model": model,
    }

    # Use either fields or exclude, not both
    if exclude_fields:
        meta_attrs["exclude"] = exclude_fields
    else:
        meta_attrs["fields"] = "__all__"

    # Check if this model has polymorphic children
    analysis = inheritance_handler.analyze_model_inheritance(model)

    type_attrs["Meta"] = type("Meta", (), meta_attrs)

    # Add polymorphic type resolution for base models
    if analysis and analysis.get("child_models"):
        # This is a polymorphic base model, add custom type resolution
        def is_type_of(root, info):
            """
            Custom type resolution for polymorphic models.
            Returns True if the instance can be represented by this type.
            """
            # For polymorphic base types, accept both base and child instances
            return isinstance(root, model)

        type_attrs["is_type_of"] = staticmethod(is_type_of)

        # Add polymorphic_type field to indicate the actual class name
        type_attrs["polymorphic_type"] = graphene.String(
            description="The actual class name of this polymorphic instance"
        )

        def resolve_polymorphic_type(self, info):
            """
            Resolver for polymorphic_type field.
            Returns the actual class name of the instance.
            """
            return self.__class__.__name__

        type_attrs["resolve_polymorphic_type"] = resolve_polymorphic_type

    model_type = type(class_name, (DjangoObjectType,), type_attrs)

    # For polymorphic models, don't add interface logic here
    # Union types will be handled at the query level

    self._type_registry[model] = model_type
    return model_type
