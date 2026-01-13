"""
Unit tests for PDF templating utilities.
"""

from dataclasses import dataclass

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from rail_django.extensions.templating import (
    PdfTemplatePreviewView,
    TemplateDefinition,
    WEASYPRINT_AVAILABLE,
    evaluate_template_access,
    model_pdf_template,
    pdf_template,
    render_pdf,
    template_registry,
    _register_model_templates,
)
from rail_django.extensions.auth import JWTManager

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
