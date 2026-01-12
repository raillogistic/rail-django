"""
Unit tests for PDF templating utilities.
"""

from dataclasses import dataclass

from django.test import TestCase

from rail_django.extensions.templating import (
    TemplateDefinition,
    evaluate_template_access,
    model_pdf_template,
    template_registry,
    _register_model_templates,
)


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
