"""
Excel export URL patterns.

This module provides URL patterns for the Excel export endpoints.
"""

from django.urls import path

from .config import _url_prefix
from .job_views import (
    ExcelTemplateJobDownloadView,
    ExcelTemplateJobStatusView,
)
from .views import (
    ExcelTemplateCatalogView,
    ExcelTemplateView,
)


def excel_urlpatterns():
    """
    Return URL patterns to expose Excel template endpoints under the configured prefix.

    The final URL shape is:
        /api/<prefix>/<template_path>/
        /api/<prefix>/<template_path>/?pk=<pk>

    Where <template_path> defaults to <app_label>/<model_name>/<function_name>.
    The pk parameter is passed as a query parameter.

    Returns:
        List of URL patterns for Excel endpoints.
    """
    prefix = _url_prefix().rstrip("/")
    return [
        path(
            f"{prefix}/catalog/",
            ExcelTemplateCatalogView.as_view(),
            name="excel_template_catalog",
        ),
        path(
            f"{prefix}/jobs/<uuid:job_id>/",
            ExcelTemplateJobStatusView.as_view(),
            name="excel_template_job_status",
        ),
        path(
            f"{prefix}/jobs/<uuid:job_id>/download/",
            ExcelTemplateJobDownloadView.as_view(),
            name="excel_template_job_download",
        ),
        path(
            f"{prefix}/<path:template_path>/",
            ExcelTemplateView.as_view(),
            name="excel_template",
        ),
    ]


__all__ = [
    "excel_urlpatterns",
]
