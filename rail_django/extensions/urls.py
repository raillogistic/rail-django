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

This will make the export endpoints available at: /api/export/

Export endpoints require JWT auth; missing auth decorators will raise
ImproperlyConfigured when importing export URLs.
"""

from .exporting import get_export_urls
from .templating import template_urlpatterns

app_name = "rail_django_extensions"

urlpatterns = get_export_urls()

urlpatterns += template_urlpatterns()
