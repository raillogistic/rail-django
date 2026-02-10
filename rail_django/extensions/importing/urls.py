"""URL patterns for importing extension."""

from django.urls import path

from .views import ModelImportTemplateDownloadView


def importing_urlpatterns():
    return [
        path(
            "import/templates/<str:app_label>/<str:model_name>/",
            ModelImportTemplateDownloadView.as_view(),
            name="model_import_template_download",
        ),
    ]


__all__ = ["importing_urlpatterns"]

