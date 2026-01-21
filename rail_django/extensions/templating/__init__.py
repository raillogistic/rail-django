"""
PDF templating helpers built on top of WeasyPrint with pluggable renderers.

This module lets models expose printable PDFs by decorating a model method with
`@model_pdf_template`. The decorator registers a dynamic Django view that:
- Finds the related model instance (by PK passed in the URL)
- Renders header/content/footer templates with the instance context and the
  return value of the decorated method
- Applies optional style configuration (margins, fonts, spacing, etc.)
- Streams the generated PDF with the configured renderer
- Supports async jobs, catalog/preview endpoints, and optional post-processing

Usage inside a model:
    from rail_django.extensions.templating import model_pdf_template

    class WorkOrder(models.Model):
        ...

        @model_pdf_template(
            content="pdf/workorders/detail.html",
            header="pdf/shared/header.html",
            footer="pdf/shared/footer.html",
            url="workorders/printable/detail",
            config={"margin": "15mm", "font_family": "Inter, sans-serif"},
        )
        def printable_detail(self):
            return {"title": f"OT #{self.pk}", "lines": self.lines.all()}

The view is automatically available at:
    /api/templates/workorders/printable/detail/<pk>/

If `url` is omitted, the default path is: <app_label>/<model_name>/<function_name>.
Default header/footer templates and style configuration come from
`settings.RAIL_DJANGO_GRAPHQL_TEMPLATING`.
"""

# Re-export all public APIs for backward compatibility

# Registry and decorators
from .registry import (
    TemplateMeta,
    TemplateDefinition,
    TemplateAccessDecision,
    TemplateRegistry,
    template_registry,
    model_pdf_template,
    pdf_template,
    _register_model_templates,
)

# Access control
from .access import (
    evaluate_template_access,
    authorize_template_access,
)

# Rendering
from .rendering import (
    render_pdf,
    render_pdf_from_html,
    render_template_html,
    PdfBuilder,
    PdfRenderer,
    WeasyPrintRenderer,
    WkhtmltopdfRenderer,
    register_pdf_renderer,
    get_pdf_renderer,
    WEASYPRINT_AVAILABLE,
)

# Views
from .views import (
    PdfTemplateView,
    PdfTemplatePreviewView,
    PdfTemplateCatalogView,
)
from .job_views import (
    PdfTemplateJobStatusView,
    PdfTemplateJobDownloadView,
)

# URL patterns
from .urls import template_urlpatterns

# Async jobs
from .jobs import generate_pdf_async

__all__ = [
    # Registry and decorators
    "TemplateMeta",
    "TemplateDefinition",
    "TemplateAccessDecision",
    "TemplateRegistry",
    "template_registry",
    "model_pdf_template",
    "pdf_template",
    "_register_model_templates",
    # Access control
    "evaluate_template_access",
    "authorize_template_access",
    # Rendering
    "render_pdf",
    "render_pdf_from_html",
    "render_template_html",
    "PdfBuilder",
    "PdfRenderer",
    "WeasyPrintRenderer",
    "WkhtmltopdfRenderer",
    "register_pdf_renderer",
    "get_pdf_renderer",
    "WEASYPRINT_AVAILABLE",
    # Views
    "PdfTemplateView",
    "PdfTemplatePreviewView",
    "PdfTemplateCatalogView",
    "PdfTemplateJobStatusView",
    "PdfTemplateJobDownloadView",
    # URL patterns
    "template_urlpatterns",
    # Async jobs
    "generate_pdf_async",
]
