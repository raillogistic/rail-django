import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta
from rail_django.extensions.form.extractors.base import FormConfigExtractor
from rail_django.security.rbac import role_manager
from test_app.models import Product

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class _RelationMetaStub:
    def __init__(self, relation_config):
        self._relation_config = relation_config

    def get_relation_config(self, field_name: str):
        if field_name == "category":
            return self._relation_config
        return None


def test_relation_operation_permissions_resolve_with_rbac_permission_checks():
    extractor = FormConfigExtractor(schema_name="default")
    category_field = Product._meta.get_field("category")
    relation_config = RailGraphQLMeta.FieldRelation(
        connect=RailGraphQLMeta.RelationOperation(
            enabled=True,
            require_permission="test_app.change_category",
        ),
        create=RailGraphQLMeta.RelationOperation(enabled=False),
        update=RailGraphQLMeta.RelationOperation(enabled=False),
        disconnect=RailGraphQLMeta.RelationOperation(enabled=False),
        set=RailGraphQLMeta.RelationOperation(
            enabled=True,
            require_permission="test_app.change_category",
        ),
    )

    User = get_user_model()
    user = User.objects.create_user(
        username="relation_perm_user",
        password="pass12345",
    )

    denied = extractor._extract_relation_operations(
        Product,
        "category",
        field=category_field,
        is_to_many=False,
        is_reverse=False,
        graphql_meta=_RelationMetaStub(relation_config),
        user=user,
    )
    assert denied["can_connect"] is False
    assert denied["can_set"] is False
    assert denied["connect_permission"] == "test_app.change_category"
    assert denied["set_permission"] == "test_app.change_category"
    assert denied["connect_reason"]
    assert denied["set_reason"]
    assert denied["can_create"] is False
    assert denied["can_update"] is False

    user.user_permissions.add(
        Permission.objects.get(
            codename="change_category",
            content_type__app_label="test_app",
        )
    )
    user = User.objects.get(pk=user.pk)
    role_manager.invalidate_user_cache(user)

    allowed = extractor._extract_relation_operations(
        Product,
        "category",
        field=category_field,
        is_to_many=False,
        is_reverse=False,
        graphql_meta=_RelationMetaStub(relation_config),
        user=user,
    )
    assert allowed["can_connect"] is True
    assert allowed["can_set"] is True
    assert allowed["connect_reason"] is None
    assert allowed["set_reason"] is None
