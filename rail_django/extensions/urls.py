"""
URL Configuration for Django Model Export Extension

This module provides URL patterns for the model export functionality.
Include these URLs in your main Django project to enable the /export endpoint.

Usage in your main urls.py:
    from django.urls import path, include

    urlpatterns = [
        path('admin/', admin.site.urls),
        path('api/', include('rail_django.extensions.urls')),
        # ... other patterns
    ]

This will make the export endpoint available at: /api/export/
"""

from django.urls import path

from .exporting import ExportView
from .templating import template_urlpatterns

app_name = "rail_django_extensions"

urlpatterns = [
    path("export/", ExportView.as_view(), name="model_export"),
]

urlpatterns += template_urlpatterns()
