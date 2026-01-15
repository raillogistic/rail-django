"""
Tests for mutation security and validation behaviors.
"""

import copy

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from graphql import GraphQLError

from rail_django.core.exceptions import ValidationError as GraphQLValidationError
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig
from rail_django.core.middleware import FieldPermissionMiddleware
from rail_django.core.settings import MutationGeneratorSettings
from rail_django.generators.introspector import ModelIntrospector
from rail_django.generators.mutations import MutationGenerator
from rail_django.generators.types import TypeGenerator
from rail_django.security.field_permissions import (
    FieldAccessLevel,
    FieldVisibility,
    FieldPermissionRule,
    field_permission_manager,
)
from test_app.models import Category, Post

pytestmark = pytest.mark.unit


def _set_graphql_meta(model, meta_class):
    original = getattr(model, "GraphQLMeta", None)
    if hasattr(model, "_graphql_meta_instance"):
        delattr(model, "_graphql_meta_instance")
    model.GraphQLMeta = meta_class
    return original


def _restore_graphql_meta(model, original):
    if original is None:
        if hasattr(model, "GraphQLMeta"):
            delattr(model, "GraphQLMeta")
    else:
        model.GraphQLMeta = original
    if hasattr(model, "_graphql_meta_instance"):
        delattr(model, "_graphql_meta_instance")


def _info_stub(user, *, model_class, field_name):
    return SimpleNamespace(
        context=SimpleNamespace(user=user),
        field_name=field_name,
        operation=SimpleNamespace(operation=SimpleNamespace(value="mutation")),
        return_type=SimpleNamespace(
            graphene_type=SimpleNamespace(model_class=model_class)
        ),
    )


def test_update_input_id_is_optional():
    type_generator = TypeGenerator()
    update_input = type_generator.generate_input_type(
        Category, "update", partial=True
    )
    fields = update_input._meta.fields
    assert "id" in fields
    id_field = fields["id"]
    assert not hasattr(id_field._type, "_of_type")


def test_nested_fields_respect_disable_nested_relations():
    settings = MutationGeneratorSettings(enable_nested_relations=False)
    type_generator = TypeGenerator(mutation_settings=settings)
    create_input = type_generator.generate_input_type(Post, "create")
    fields = create_input._meta.fields
    assert "nested_category" not in fields
    assert "nested_tags" not in fields
    assert "nested_comments" not in fields


@pytest.mark.django_db
def test_bulk_create_inherits_create_guard():
    class GuardedMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.AccessControl(
            operations={"create": GraphQLMetaConfig.OperationGuard()}
        )

    original_meta = _set_graphql_meta(Category, GuardedMeta)
    try:
        generator = MutationGenerator(TypeGenerator())
        bulk_mutation = generator.generate_bulk_create_mutation(Category)
        info = SimpleNamespace(context=SimpleNamespace(user=AnonymousUser()))
        result = bulk_mutation.mutate(
            None,
            info,
            inputs=[{"name": "alpha", "description": ""}],
        )
        assert result.ok is False
        assert result.errors
        assert "Authentication required" in result.errors[0].message
    finally:
        _restore_graphql_meta(Category, original_meta)


@pytest.mark.django_db
def test_method_mutation_enforces_operation_guard():
    class GuardedMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.AccessControl(
            operations={"update": GraphQLMetaConfig.OperationGuard()}
        )

    def _activate(self):
        return True

    original_meta = _set_graphql_meta(Category, GuardedMeta)
    original_method = getattr(Category, "activate", None)
    Category.activate = _activate
    if hasattr(Category, "_graphql_meta_instance"):
        delattr(Category, "_graphql_meta_instance")

    try:
        category = Category.objects.create(name="alpha", description="")
        generator = MutationGenerator(TypeGenerator())
        introspector = ModelIntrospector(Category)
        method_info = introspector.get_model_methods()["activate"]
        mutation_class = generator.generate_method_mutation(Category, method_info)
        info = SimpleNamespace(context=SimpleNamespace(user=AnonymousUser()))
        result = mutation_class.mutate(None, info, id=category.id)
        assert result.ok is False
        assert result.errors
        assert "Authentication required" in result.errors[0].message
    finally:
        if original_method is None:
            delattr(Category, "activate")
        else:
            Category.activate = original_method
        _restore_graphql_meta(Category, original_meta)


@pytest.mark.django_db
def test_nested_create_enforces_related_guard():
    class GuardedMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.AccessControl(
            operations={"create": GraphQLMetaConfig.OperationGuard()}
        )

    original_meta = _set_graphql_meta(Category, GuardedMeta)
    try:
        generator = MutationGenerator(TypeGenerator())
        create_mutation = generator.generate_create_mutation(Post)
        info = SimpleNamespace(context=SimpleNamespace(user=AnonymousUser()))
        result = create_mutation.mutate(
            None,
            info,
            input={
                "title": "hello",
                "nested_category": {"name": "news", "description": ""},
            },
        )
        assert result.ok is False
        assert result.errors
        assert "Authentication required" in result.errors[0].message
    finally:
        _restore_graphql_meta(Category, original_meta)


@pytest.mark.django_db
def test_create_mutation_requires_model_permission():
    generator = MutationGenerator(TypeGenerator())
    create_mutation = generator.generate_create_mutation(Category)
    user = User.objects.create_user(username="perm_user", password="pass12345")
    info = SimpleNamespace(context=SimpleNamespace(user=user))
    result = create_mutation.mutate(
        None,
        info,
        input={"name": "alpha", "description": ""},
    )
    assert result.ok is False
    assert result.errors
    message = result.errors[0].message
    assert "permission" in message.lower()
    assert "test_app.add_category" in message


@pytest.mark.django_db
def test_field_permission_middleware_checks_nested_fields():
    user = User.objects.create_user(username="nested_user", password="pass12345")
    content_type = ContentType.objects.get_for_model(Post)
    perm = Permission.objects.get(codename="change_post", content_type=content_type)
    user.user_permissions.add(perm)

    snapshot = {
        "field_rules": copy.deepcopy(field_permission_manager._field_rules),
        "pattern_rules": copy.deepcopy(field_permission_manager._pattern_rules),
        "global_rules": list(field_permission_manager._global_rules),
        "rule_signatures": set(field_permission_manager._rule_signatures),
    }
    try:
        field_permission_manager.register_field_rule(
            FieldPermissionRule(
                field_name="name",
                model_name="test_app.category",
                access_level=FieldAccessLevel.READ,
                visibility=FieldVisibility.VISIBLE,
            )
        )

        middleware = FieldPermissionMiddleware()
        middleware.input_mode = "reject"
        middleware.enable_field_permissions = True

        info = _info_stub(user, model_class=Post, field_name="update_post")
        with pytest.raises(GraphQLError):
            middleware._enforce_input_permissions(
                user,
                info,
                {"input": {"nested_category": {"name": "blocked"}}},
            )
    finally:
        field_permission_manager._field_rules = snapshot["field_rules"]
        field_permission_manager._pattern_rules = snapshot["pattern_rules"]
        field_permission_manager._global_rules = snapshot["global_rules"]
        field_permission_manager._rule_signatures = snapshot["rule_signatures"]


@pytest.mark.django_db
def test_full_clean_runs_for_create_mutation():
    def _clean(self):
        if self.name == "invalid":
            raise DjangoValidationError({"name": "invalid name"})

    original_clean = getattr(Category, "clean", None)
    Category.clean = _clean
    try:
        generator = MutationGenerator(TypeGenerator())
        create_mutation = generator.generate_create_mutation(Category)
        info = SimpleNamespace(
            context=SimpleNamespace(user=User(is_superuser=True))
        )
        result = create_mutation.mutate(
            None,
            info,
            input={"name": "invalid", "description": ""},
        )
        assert result.ok is False
        assert result.errors
        assert "invalid name" in result.errors[0].message
    finally:
        if original_clean is None:
            delattr(Category, "clean")
        else:
            Category.clean = original_clean


@pytest.mark.django_db
def test_input_validator_errors_surface_in_mutations():
    class _StubValidator:
        def validate_and_sanitize(self, model_name, input_data):
            raise GraphQLValidationError("invalid input", field="name")

    generator = MutationGenerator(TypeGenerator())
    generator.input_validator = _StubValidator()
    create_mutation = generator.generate_create_mutation(Category)
    info = SimpleNamespace(
        context=SimpleNamespace(user=User(is_superuser=True))
    )
    result = create_mutation.mutate(
        None,
        info,
        input={"name": "alpha", "description": ""},
    )
    assert result.ok is False
    assert result.errors
    assert result.errors[0].field == "name"
