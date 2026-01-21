"""
URL patterns for PDF template endpoints.

This module provides the URL patterns for the PDF templating system
including catalog, preview, job status, job download, and template rendering.
"""

from django.urls import path

from .config import _url_prefix
from .views import (
    PdfTemplateCatalogView,
    PdfTemplatePreviewView,
    PdfTemplateView,
)
from .job_views import (
    PdfTemplateJobDownloadView,
    PdfTemplateJobStatusView,
)


def template_urlpatterns():
    """
    Return URL patterns to expose template endpoints under the configured prefix.

    The final URL shape is:
        /api/<prefix>/<template_path>/<pk>/

    Where <template_path> defaults to <app_label>/<model_name>/<function_name>.
    """
    prefix = _url_prefix().rstrip("/")
    return [
        path(
            f"{prefix}/catalog/",
            PdfTemplateCatalogView.as_view(),
            name="pdf_template_catalog",
        ),
        path(
            f"{prefix}/preview/<path:template_path>/<str:pk>/",
            PdfTemplatePreviewView.as_view(),
            name="pdf_template_preview",
        ),
        path(
            f"{prefix}/jobs/<uuid:job_id>/",
            PdfTemplateJobStatusView.as_view(),
            name="pdf_template_job_status",
        ),
        path(
            f"{prefix}/jobs/<uuid:job_id>/download/",
            PdfTemplateJobDownloadView.as_view(),
            name="pdf_template_job_download",
        ),
        path(
            f"{prefix}/<path:template_path>/<str:pk>/",
            PdfTemplateView.as_view(),
            name="pdf_template",
        )
    ]
