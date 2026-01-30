"""Export URL Configuration

This module provides URL patterns for the export functionality.
"""

from django.core.exceptions import ImproperlyConfigured
from django.urls import path

from .security import JWT_REQUIRED_AVAILABLE
from .views import ExportJobDownloadView, ExportJobStatusView, ExportView


def get_export_urls():
    """Helper function to get URL patterns for the export functionality.

    Usage in urls.py:
        from rail_django.extensions.exporting import get_export_urls

        urlpatterns = [
            # ... other patterns
        ] + get_export_urls()

    Returns:
        List of URL patterns (export + async job endpoints).

    Raises:
        ImproperlyConfigured: If JWT auth is not available.
    """
    if not JWT_REQUIRED_AVAILABLE:
        raise ImproperlyConfigured(
            "Export endpoints require JWT auth; rail_django.extensions.auth.decorators is missing."
        )

    return [
        path("export/", ExportView.as_view(), name="model_export"),
        path(
            "export/jobs/<uuid:job_id>/",
            ExportJobStatusView.as_view(),
            name="export_job_status",
        ),
        path(
            "export/jobs/<uuid:job_id>/download/",
            ExportJobDownloadView.as_view(),
            name="export_job_download",
        ),
    ]


# Convenience: urlpatterns for direct include
urlpatterns = []
try:
    urlpatterns = get_export_urls()
except ImproperlyConfigured:
    # URL patterns will be empty if JWT auth is not configured
    pass
