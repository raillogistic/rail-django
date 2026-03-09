"""
Unit tests for PDF templating utilities.
"""

from dataclasses import dataclass
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.template import TemplateDoesNotExist
from django.test import RequestFactory, TestCase, override_settings

from rail_django.extensions.templating import (
    PdfTemplateCatalogView,
    PdfTemplatePreviewView,
    TemplateDefinition,
    WEASYPRINT_AVAILABLE,
    evaluate_template_access,
    model_pdf_template,
    pdf_template,
    render_pdf,
    render_pdf_from_html,
    template_registry,
    _register_model_templates,
)
from rail_django.extensions.auth import JWTManager
from rail_django.extensions.templating.rendering.html import render_template_html

pytestmark = pytest.mark.unit


@dataclass
class DummyMeta:
    app_label: str = "testapp"
    model_name: str = "dummy"
    label: str = "testapp.Dummy"
    label_lower: str = "testapp.dummy"
    verbose_name: str = "Dummy"
    abstract: bool = False


class DummyUser:
    def __init__(self, *, is_authenticated, perms=None, is_superuser=False):
        self.is_authenticated = is_authenticated
        self._perms = set(perms or [])
        self.is_superuser = is_superuser

    def has_perm(self, perm):
        return perm in self._perms


class TestTemplatingRegistry(TestCase):
    def setUp(self):
        self._original_templates = template_registry.all()

    def tearDown(self):
        template_registry._templates = dict(self._original_templates)

    def test_registers_inherited_template_methods(self):
        class BaseModel:
            @model_pdf_template(content="pdf/base.html")
            def printable_base(self):
                return {"ok": True}

        class DerivedModel(BaseModel):
            _meta = DummyMeta()

        _register_model_templates(DerivedModel)
        template = template_registry.get("testapp/dummy/printable_base")
        self.assertIsNotNone(template)


class TestTemplateAccess(TestCase):
    def test_permission_denied_for_missing_permissions(self):
        template_def = TemplateDefinition(
            model=None,
            method_name=None,
            handler=None,
            source="function",
            header_template="pdf/header.html",
            content_template="pdf/content.html",
            footer_template="pdf/footer.html",
            url_path="test/template",
            config={},
            roles=(),
            permissions=("testapp.view_dummy",),
            guard=None,
            require_authentication=True,
            title="Dummy",
            allow_client_data=False,
            client_data_fields=(),
            client_data_schema=(),
            repeat_header=True,
            repeat_footer=True,
        )
        user = DummyUser(is_authenticated=True, perms=[])
        decision = evaluate_template_access(template_def, user=user, instance=None)
        self.assertFalse(decision.allowed)

    def test_permission_allows_when_authenticated(self):
        template_def = TemplateDefinition(
            model=None,
            method_name=None,
            handler=None,
            source="function",
            header_template="pdf/header.html",
            content_template="pdf/content.html",
            footer_template="pdf/footer.html",
            url_path="test/template",
            config={},
            roles=(),
            permissions=(),
            guard=None,
            require_authentication=True,
            title="Dummy",
            allow_client_data=False,
            client_data_fields=(),
            client_data_schema=(),
            repeat_header=True,
            repeat_footer=True,
        )
        user = DummyUser(is_authenticated=True)
        decision = evaluate_template_access(template_def, user=user, instance=None)
        self.assertTrue(decision.allowed)


class TestTemplatingRendering(TestCase):
    def setUp(self):
        self._original_templates = template_registry.all()

    def tearDown(self):
        template_registry._templates = dict(self._original_templates)

    @pytest.mark.skipif(not WEASYPRINT_AVAILABLE, reason="WeasyPrint not available")
    def test_render_pdf_from_templates(self):
        templates = {
            "pdf/header.html": "<div>Header {{ data.title }}</div>",
            "pdf/content.html": "<div>Content {{ data.title }}</div>",
            "pdf/footer.html": "<div>Footer</div>",
        }

        with override_settings(
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "DIRS": [],
                    "APP_DIRS": False,
                    "OPTIONS": {
                        "loaders": [
                            ("django.template.loaders.locmem.Loader", templates)
                        ]
                    },
                }
            ],
            RAIL_DJANGO_GRAPHQL_TEMPLATING={
                "default_header_template": "pdf/header.html",
                "default_footer_template": "pdf/footer.html",
            },
        ):
            pdf_bytes = render_pdf(
                "pdf/content.html",
                {"data": {"title": "Sample"}},
                header_template="pdf/header.html",
                footer_template="pdf/footer.html",
            )

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 200)

    def test_preview_view_renders_html(self):
        templates = {
            "pdf/header.html": "<div>Header {{ data.title }}</div>",
            "pdf/content.html": "<div>Content {{ data.title }}</div>",
            "pdf/footer.html": "<div>Footer</div>",
        }

        with override_settings(
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "DIRS": [],
                    "APP_DIRS": False,
                    "OPTIONS": {
                        "loaders": [
                            ("django.template.loaders.locmem.Loader", templates)
                        ]
                    },
                }
            ],
            RAIL_DJANGO_GRAPHQL_TEMPLATING={"enable_preview": True},
        ):

            @pdf_template(
                content="pdf/content.html",
                header="pdf/header.html",
                footer="pdf/footer.html",
                url="testing/preview",
                require_authentication=False,
            )
            def preview_template(request, pk):
                return {"title": f"Item {pk}"}

            User = get_user_model()
            user = User.objects.create_user(
                username="preview_user", password="pass12345"
            )
            token = JWTManager.generate_token(user)["token"]
            request = RequestFactory().get(
                "/api/templates/testing/preview/1/",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
            response = PdfTemplatePreviewView.as_view()(
                request, template_path="testing/preview", pk="1"
            )

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Header", body)
        self.assertIn("Content", body)

    def test_render_template_html_pins_header_and_footer_for_each_page(self):
        html = render_template_html(
            header_html="<div>Header</div>",
            content_html="<div>Content</div>",
            footer_html="<div>Footer</div>",
            config={
                "header_height": "20mm",
                "footer_height": "20mm",
                "header_spacing": "10mm",
                "footer_spacing": "12mm",
            },
        )

        self.assertIn("margin-top: calc(20mm + calc(20mm + 10mm));", html)
        self.assertIn("margin-bottom: calc(20mm + calc(20mm + 12mm));", html)
        self.assertIn(".pdf-header { position: fixed;", html)
        self.assertIn("top: calc(-1 * calc(20mm + 10mm));", html)
        self.assertIn("left: 0;", html)
        self.assertIn(".pdf-footer { position: fixed;", html)
        self.assertIn("bottom: calc(-1 * calc(20mm + 12mm));", html)
        self.assertNotIn(".pdf-header { margin-bottom:", html)
        self.assertNotIn(".pdf-footer { margin-top:", html)
        self.assertNotIn("min-height: 20mm;", html)
        self.assertIn("<div class='pdf-header'><div>Header</div></div>", html)
        self.assertIn("<div class='pdf-footer'><div>Footer</div></div>", html)

    def test_render_template_html_does_not_reserve_header_footer_space_by_default(self):
        html = render_template_html(
            header_html="<div>Header</div>",
            content_html="<div>Content</div>",
            footer_html="<div>Footer</div>",
            config={},
        )

        self.assertIn("margin-top: calc(20mm + calc(0mm + 0mm));", html)
        self.assertIn("margin-bottom: calc(20mm + calc(0mm + 0mm));", html)
        self.assertIn("top: calc(-1 * calc(0mm + 0mm));", html)
        self.assertIn("bottom: calc(-1 * calc(0mm + 0mm));", html)

    def test_render_template_html_can_limit_header_and_footer_to_first_page(self):
        html = render_template_html(
            header_html="<div>Header</div>",
            content_html="<div>Content</div>",
            footer_html="<div>Footer</div>",
            repeat_header=None,
            repeat_footer=None,
            config={
                "header_height": "20mm",
                "footer_height": "20mm",
                "header_spacing": "10mm",
                "footer_spacing": "12mm",
            },
        )

        self.assertIn(
            "@page { margin-top: calc(20mm + 0mm); margin-right: 20mm; margin-bottom: calc(20mm + 0mm); margin-left: 20mm; }",
            html,
        )
        self.assertIn(
            "@page :first { margin-top: calc(20mm + calc(20mm + 10mm)); @top-center { content: element(pdf-header); vertical-align: top; margin: 0; padding: 0; } }",
            html,
        )
        self.assertIn(
            "@page :first { margin-bottom: calc(20mm + calc(20mm + 12mm)); @bottom-center { content: element(pdf-footer); vertical-align: bottom; margin: 0; padding: 0; } }",
            html,
        )
        self.assertIn(
            ".pdf-header { position: running(pdf-header); height: 0; min-height: 0; margin: 0; padding: 0; overflow: visible; }",
            html,
        )
        self.assertIn(
            ".pdf-footer { position: running(pdf-footer); height: 0; min-height: 0; margin: 0; padding: 0; overflow: visible; }",
            html,
        )
        self.assertIn("<div class='pdf-header'><div>Header</div></div>", html)
        self.assertIn("<div class='pdf-footer'><div>Footer</div></div>", html)

    def test_render_template_html_extracts_fragment_styles_before_wrapper_css(self):
        html = render_template_html(
            header_html="<div>Header</div>",
            content_html="""
                <!doctype html>
                <html>
                  <head>
                    <style>
                      @page {
                        margin-top: 3.5cm;
                        margin-bottom: 3.5cm;
                        margin-left: 1cm;
                        margin-right: 1cm;
                      }
                      .document { padding-top: 10px; }
                    </style>
                  </head>
                  <body><div class="document">Content</div></body>
                </html>
            """,
            footer_html="<div>Footer</div>",
            repeat_header=None,
            repeat_footer=None,
            config={
                "header_height": "20mm",
                "footer_height": "20mm",
                "header_spacing": "10mm",
                "footer_spacing": "12mm",
            },
        )

        self.assertIn(".document { padding-top: 10px; }", html)
        self.assertIn(
            "@page { margin-top: calc(20mm + 0mm); margin-right: 20mm; margin-bottom: calc(20mm + 0mm); margin-left: 20mm; }",
            html,
        )
        self.assertIn(
            "@page :first { margin-top: calc(20mm + calc(20mm + 10mm)); @top-center { content: element(pdf-header); vertical-align: top; margin: 0; padding: 0; } }",
            html,
        )
        self.assertNotIn("<div class='pdf-content'><html>", html)
        self.assertNotIn("<div class='pdf-content'><body>", html)

    def test_model_pdf_template_stores_repeat_flags(self):
        @model_pdf_template(
            content="pdf/base.html",
            repeat_header=None,
            repeat_footer=None,
        )
        def printable_base(self):
            return {"ok": True}

        meta = printable_base._pdf_template_meta
        self.assertIsNone(meta.repeat_header)
        self.assertIsNone(meta.repeat_footer)

    @patch("rail_django.extensions.templating.rendering.renderers.shutil.which")
    def test_wkhtmltopdf_is_blocked_without_explicit_unsafe_opt_in(
        self,
        mock_which,
    ):
        mock_which.return_value = "wkhtmltopdf"

        with self.assertRaises(RuntimeError) as exc:
            render_pdf_from_html(
                "<html><body>Hello</body></html>",
                renderer="wkhtmltopdf",
            )

        self.assertIn("cannot enforce Rail Django URL fetch allowlists", str(exc.exception))

    @patch("rail_django.extensions.templating.rendering.renderers.subprocess.run")
    @patch("rail_django.extensions.templating.rendering.renderers.shutil.which")
    def test_wkhtmltopdf_allows_explicit_unrestricted_fetch_opt_in(
        self,
        mock_which,
        mock_run,
    ):
        mock_which.return_value = "wkhtmltopdf"

        def _fake_run(args, check, stdout, stderr):
            pdf_path = args[-1]
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n%mock\n")
            return None

        mock_run.side_effect = _fake_run

        pdf_bytes = render_pdf_from_html(
            "<html><body>Hello</body></html>",
            renderer="wkhtmltopdf",
            config={"wkhtmltopdf_allow_unrestricted_fetch": True},
        )

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        mock_run.assert_called_once()


class TestTemplateCatalogView(TestCase):
    def setUp(self):
        self._original_templates = template_registry.all()

    def tearDown(self):
        template_registry._templates = dict(self._original_templates)

    def _seed_template(self):
        template_registry._templates = {
            "testapp/dummy/printable_base": TemplateDefinition(
                model=None,
                method_name=None,
                handler=lambda request, pk: {"ok": True},
                source="function",
                header_template="pdf/header.html",
                content_template="pdf/content.html",
                footer_template="pdf/footer.html",
                url_path="testapp/dummy/printable_base",
                config={},
                roles=(),
                permissions=(),
                guard=None,
                require_authentication=False,
                title="Printable base",
                allow_client_data=False,
                client_data_fields=(),
                client_data_schema=(),
                repeat_header=True,
                repeat_footer=True,
            )
        }

    @override_settings(
        RAIL_DJANGO_GRAPHQL_TEMPLATING={"catalog": {"require_authentication": False}}
    )
    def test_catalog_returns_html_for_browser_accept_header(self):
        self._seed_template()
        request = RequestFactory().get(
            "/api/v1/templates/catalog/",
            HTTP_ACCEPT="text/html,application/xhtml+xml",
        )

        response = PdfTemplateCatalogView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        body = response.content.decode("utf-8")
        self.assertIn("/api/v1/templates/catalog/", body)
        self.assertIn("testapp/dummy/printable_base", body)

    @override_settings(
        RAIL_DJANGO_GRAPHQL_TEMPLATING={"catalog": {"require_authentication": False}}
    )
    def test_catalog_returns_json_for_api_accept_header(self):
        self._seed_template()
        request = RequestFactory().get(
            "/api/v1/templates/catalog/",
            HTTP_ACCEPT="application/json",
        )

        response = PdfTemplateCatalogView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])
        self.assertIn("templates", response.content.decode("utf-8"))

    @override_settings(
        RAIL_DJANGO_GRAPHQL_TEMPLATING={"catalog": {"require_authentication": False}}
    )
    def test_catalog_html_fallback_when_template_missing(self):
        self._seed_template()
        request = RequestFactory().get(
            "/api/v1/templates/catalog/",
            HTTP_ACCEPT="text/html",
        )

        with patch(
            "rail_django.extensions.templating.views.render",
            side_effect=TemplateDoesNotExist("templating_catalog.html"),
        ):
            response = PdfTemplateCatalogView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        body = response.content.decode("utf-8")
        self.assertIn("PDF Templates Catalog", body)
        self.assertIn("/api/v1/templates/testapp/dummy/printable_base/&lt;pk&gt;/", body)

