from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from rail_django.extensions.metadata.extractor import ModelSchemaExtractor
from rail_django.extensions.metadata.queries import ModelSchemaQuery
from rail_django.extensions.templating.registry import TemplateAccessDecision
from rail_django.security.field_permissions import FieldVisibility
from test_app.models import Product


def _build_model(app_label: str, model_name: str):
    meta = SimpleNamespace(
        app_label=app_label,
        model_name=model_name.lower(),
        verbose_name=model_name,
        verbose_name_plural=f"{model_name}s",
    )
    return SimpleNamespace(_meta=meta, __name__=model_name)


class TestMetadataSecurityHardening(TestCase):
    @patch("rail_django.extensions.metadata.queries.get_model_graphql_meta")
    def test_available_models_filters_by_user_capabilities(self, mock_get_meta):
        model_allowed = _build_model("inventory", "Product")
        model_denied = _build_model("inventory", "Secret")

        mock_meta = MagicMock()
        mock_meta.describe_operation_guard.return_value = {
            "guarded": False,
            "allowed": True,
            "reason": None,
        }
        mock_get_meta.return_value = mock_meta

        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        user.has_perm.side_effect = lambda perm: perm == "inventory.view_product"

        info = SimpleNamespace(context=SimpleNamespace(user=user))

        with patch(
            "rail_django.extensions.metadata.queries.apps.get_models",
            return_value=[model_allowed, model_denied],
        ):
            results = ModelSchemaQuery().resolve_availableModels(info)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["model"], "Product")

    @patch("rail_django.extensions.metadata.queries.get_model_graphql_meta")
    def test_available_models_allows_anonymous_only_when_guard_explicitly_allows(
        self, mock_get_meta
    ):
        model_public = _build_model("catalog", "PublicItem")
        model_private = _build_model("catalog", "PrivateItem")

        def describe_for_model(model):
            if model._meta.model_name == "publicitem":
                return {"guarded": True, "allowed": True, "reason": None}
            return {"guarded": False, "allowed": True, "reason": None}

        def get_meta(model):
            meta = MagicMock()
            meta.describe_operation_guard.side_effect = lambda *_args, **_kwargs: describe_for_model(model)
            return meta

        mock_get_meta.side_effect = get_meta

        info = SimpleNamespace(context=SimpleNamespace(user=None))
        with patch(
            "rail_django.extensions.metadata.queries.apps.get_models",
            return_value=[model_public, model_private],
        ):
            results = ModelSchemaQuery().resolve_availableModels(info)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["model"], "PublicItem")

    @patch("rail_django.extensions.metadata.extractor.evaluate_template_access")
    @patch("rail_django.extensions.metadata.extractor.template_registry")
    def test_template_allowed_and_denial_reason_use_server_evaluation(
        self, mock_registry, mock_evaluate_access
    ):
        model = _build_model("inventory", "Invoice")
        mock_definition = SimpleNamespace(
            model=model,
            title="Invoice",
            url_path="inventory/invoice/printable",
            guard="retrieve",
            require_authentication=True,
            roles=(),
            permissions=("inventory.view_invoice",),
            allow_client_data=False,
            client_data_fields=(),
        )
        mock_registry.all.return_value = {
            "inventory/invoice/printable": mock_definition
        }
        mock_evaluate_access.return_value = TemplateAccessDecision(
            allowed=False,
            reason="Permission manquante",
            status_code=403,
        )

        extractor = ModelSchemaExtractor()
        templates = extractor._extract_templates(model, user=MagicMock(), instance=None)

        self.assertEqual(len(templates), 1)
        self.assertFalse(templates[0]["allowed"])
        self.assertEqual(templates[0]["denial_reason"], "Permission manquante")

    @patch("rail_django.extensions.excel.access.evaluate_excel_template_access")
    @patch("rail_django.extensions.excel.exporter.excel_template_registry")
    @patch("rail_django.extensions.metadata.extractor.evaluate_template_access")
    @patch("rail_django.extensions.metadata.extractor.template_registry")
    def test_template_metadata_includes_pdf_and_excel_endpoints(
        self,
        mock_pdf_registry,
        mock_evaluate_pdf_access,
        mock_excel_registry,
        mock_evaluate_excel_access,
    ):
        model = _build_model("inventory", "Invoice")
        pdf_definition = SimpleNamespace(
            model=model,
            title="Invoice PDF",
            url_path="inventory/invoice/invoice_pdf",
            guard="retrieve",
            require_authentication=True,
            roles=("manager",),
            permissions=("inventory.view_invoice",),
            allow_client_data=True,
            client_data_fields=("include_discount",),
            client_data_schema=({"name": "notes", "type": "string"},),
        )
        excel_definition = SimpleNamespace(
            model=model,
            title="Invoice Excel",
            url_path="inventory/invoice/export_excel",
            guard="retrieve",
            require_authentication=True,
            roles=("manager",),
            permissions=("inventory.view_invoice",),
            allow_client_data=False,
            client_data_fields=("timezone",),
        )
        mock_pdf_registry.all.return_value = {
            "inventory/invoice/invoice_pdf": pdf_definition
        }
        mock_excel_registry.all.return_value = {
            "inventory/invoice/export_excel": excel_definition
        }
        mock_evaluate_pdf_access.return_value = TemplateAccessDecision(
            allowed=True,
            reason=None,
            status_code=200,
        )
        mock_evaluate_excel_access.return_value = SimpleNamespace(
            allowed=False,
            reason="Denied",
            status_code=403,
        )

        extractor = ModelSchemaExtractor()
        templates = extractor._extract_templates(model, user=MagicMock(), instance=None)

        self.assertEqual(len(templates), 2)
        pdf_template = next(item for item in templates if item["template_type"] == "pdf")
        excel_template = next(
            item for item in templates if item["template_type"] == "excel"
        )

        self.assertTrue(pdf_template["endpoint"].startswith("/api/"))
        self.assertTrue(
            pdf_template["endpoint"].endswith(
                "/templates/inventory/invoice/invoice_pdf/<pk>/"
            )
        )
        self.assertTrue(pdf_template["allowed"])
        self.assertEqual(
            pdf_template["client_data_schema"],
            [
                {"name": "notes", "type": "string"},
                {"name": "includeDiscount", "type": "string"},
            ],
        )

        self.assertTrue(excel_template["endpoint"].startswith("/api/"))
        self.assertTrue(
            excel_template["endpoint"].endswith(
                "/excel/inventory/invoice/export_excel/"
            )
        )
        self.assertFalse(excel_template["allowed"])
        self.assertEqual(excel_template["denial_reason"], "Denied")
        self.assertEqual(
            excel_template["client_data_schema"],
            [{"name": "timezone", "type": "string"}],
        )

    @patch("rail_django.extensions.metadata.filter_extractor.field_permission_manager")
    @patch("rail_django.extensions.metadata.field_extractor.field_permission_manager")
    def test_hidden_fields_are_excluded_from_metadata_and_filters(
        self,
        mock_field_perm_manager,
        mock_filter_perm_manager,
    ):
        user = MagicMock()
        user.is_authenticated = True

        visible_perm = SimpleNamespace(
            visibility=FieldVisibility.VISIBLE,
            can_write=True,
        )
        hidden_perm = SimpleNamespace(
            visibility=FieldVisibility.HIDDEN,
            can_write=False,
        )

        def _field_perm(_user, _model, field_name, instance=None):
            if field_name in {"price", "cost_price"}:
                return hidden_perm
            return visible_perm

        mock_field_perm_manager.check_field_permission.side_effect = _field_perm
        mock_filter_perm_manager.check_field_permission.side_effect = _field_perm

        extractor = ModelSchemaExtractor()
        fields = extractor._extract_fields(Product, user)
        filters = extractor._extract_filters(Product, user=user)

        field_names = {field["field_name"] for field in fields}
        filter_names = {flt["field_name"] for flt in filters}

        self.assertNotIn("price", field_names)
        self.assertNotIn("cost_price", field_names)
        self.assertNotIn("price", filter_names)
        self.assertNotIn("costPrice", filter_names)
