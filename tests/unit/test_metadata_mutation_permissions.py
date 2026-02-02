from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.db import models
from django.test import TestCase

from rail_django.core.decorators import action_form
from rail_django.core.meta.config import OperationGuardConfig
from rail_django.extensions.metadata.extractor import ModelSchemaExtractor


class PermissionTestModel(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "test_metadata_mutations"

    @action_form(permissions=["store.approve_product"])
    def approve(self):
        """Approve the product."""
        return True


class TestMetadataMutationPermissions(TestCase):
    def setUp(self):
        self.extractor = ModelSchemaExtractor()

    def _make_user(self, perms):
        user = MagicMock()
        user.is_authenticated = True

        def has_perm(value):
            return value in perms

        user.has_perm = MagicMock(side_effect=has_perm)
        return user

    @patch("rail_django.extensions.metadata.extractor.get_authz_manager")
    @patch("rail_django.extensions.metadata.extractor.MutationGeneratorSettings")
    @patch("rail_django.extensions.metadata.extractor.get_model_graphql_meta")
    def test_crud_permissions_reflected(
        self, mock_get_meta, mock_settings_cls, mock_authz_manager
    ):
        mock_authz_manager.return_value = SimpleNamespace(
            settings=SimpleNamespace(enable_authorization=True)
        )
        mock_settings = SimpleNamespace(
            enable_create=True,
            enable_update=True,
            enable_delete=True,
            require_model_permissions=True,
            model_permission_codenames={
                "create": "add",
                "update": "change",
                "delete": "delete",
            },
        )
        mock_settings_cls.from_schema.return_value = mock_settings

        meta = MagicMock()
        meta._operation_guards = {}
        meta.describe_operation_guard.return_value = {
            "guarded": False,
            "allowed": True,
            "reason": None,
        }
        mock_get_meta.return_value = meta

        user = self._make_user({"test_metadata_mutations.add_permissiontestmodel"})
        mutations = self.extractor._extract_mutations(PermissionTestModel, user)

        create_mutation = next(m for m in mutations if m["operation"] == "create")
        self.assertTrue(create_mutation["allowed"])
        self.assertTrue(create_mutation["requires_authentication"])
        self.assertEqual(
            create_mutation["required_permissions"],
            ["test_metadata_mutations.add_permissiontestmodel"],
        )

    @patch("rail_django.extensions.metadata.extractor.get_authz_manager")
    @patch("rail_django.extensions.metadata.extractor.MutationGeneratorSettings")
    @patch("rail_django.extensions.metadata.extractor.get_model_graphql_meta")
    def test_guard_overrides_permissions(
        self, mock_get_meta, mock_settings_cls, mock_authz_manager
    ):
        mock_authz_manager.return_value = SimpleNamespace(
            settings=SimpleNamespace(enable_authorization=True)
        )
        mock_settings = SimpleNamespace(
            enable_create=True,
            enable_update=False,
            enable_delete=False,
            require_model_permissions=True,
            model_permission_codenames={"create": "add"},
        )
        mock_settings_cls.from_schema.return_value = mock_settings

        guard = OperationGuardConfig(
            name="create",
            permissions=["store.add_product"],
            require_authentication=True,
            allow_anonymous=False,
        )
        meta = MagicMock()
        meta._operation_guards = {"create": guard}
        meta.describe_operation_guard.return_value = {
            "guarded": True,
            "allowed": False,
            "reason": "Nope",
        }
        mock_get_meta.return_value = meta

        user = self._make_user({"test_metadata_mutations.add_permissiontestmodel"})
        mutations = self.extractor._extract_mutations(PermissionTestModel, user)

        create_mutation = next(m for m in mutations if m["operation"] == "create")
        self.assertFalse(create_mutation["allowed"])
        self.assertTrue(create_mutation["requires_authentication"])
        self.assertEqual(create_mutation["required_permissions"], ["store.add_product"])
        self.assertEqual(create_mutation["reason"], "Nope")

    @patch("rail_django.extensions.metadata.extractor.get_authz_manager")
    @patch("rail_django.extensions.metadata.extractor.MutationGeneratorSettings")
    @patch("rail_django.extensions.metadata.extractor.get_model_graphql_meta")
    def test_method_permissions_respected(
        self, mock_get_meta, mock_settings_cls, mock_authz_manager
    ):
        mock_authz_manager.return_value = SimpleNamespace(
            settings=SimpleNamespace(enable_authorization=True)
        )
        mock_settings = SimpleNamespace(
            enable_create=False,
            enable_update=False,
            enable_delete=False,
            require_model_permissions=True,
            model_permission_codenames={},
        )
        mock_settings_cls.from_schema.return_value = mock_settings

        meta = MagicMock()
        meta._operation_guards = {}
        meta.describe_operation_guard.return_value = {
            "guarded": False,
            "allowed": True,
            "reason": None,
        }
        mock_get_meta.return_value = meta

        user = self._make_user({"store.approve_product"})
        mutations = self.extractor._extract_mutations(PermissionTestModel, user)

        approve_mutation = next(
            m for m in mutations if m["method_name"] == "approve"
        )
        self.assertTrue(approve_mutation["allowed"])
        self.assertTrue(approve_mutation["requires_authentication"])
        self.assertEqual(
            approve_mutation["required_permissions"], ["store.approve_product"]
        )

    @patch("rail_django.extensions.metadata.extractor.get_authz_manager")
    @patch("rail_django.extensions.metadata.extractor.MutationGeneratorSettings")
    @patch("rail_django.extensions.metadata.extractor.get_model_graphql_meta")
    def test_instance_passed_to_guard(
        self, mock_get_meta, mock_settings_cls, mock_authz_manager
    ):
        mock_authz_manager.return_value = SimpleNamespace(
            settings=SimpleNamespace(enable_authorization=True)
        )
        mock_settings = SimpleNamespace(
            enable_create=True,
            enable_update=True,
            enable_delete=True,
            require_model_permissions=False,
            model_permission_codenames={},
        )
        mock_settings_cls.from_schema.return_value = mock_settings

        meta = MagicMock()
        meta._operation_guards = {}
        meta.describe_operation_guard.return_value = {
            "guarded": False,
            "allowed": True,
            "reason": None,
        }
        mock_get_meta.return_value = meta

        instance = MagicMock()
        user = self._make_user(set())
        self.extractor._extract_mutations(
            PermissionTestModel, user, instance=instance
        )

        called_with_instance = any(
            kwargs.get("instance") is instance
            for _, kwargs in meta.describe_operation_guard.call_args_list
        )
        self.assertTrue(called_with_instance)
