"""
URL patterns for GraphQL health monitoring endpoints.
"""

from .views.health_views import get_health_urls

health_urlpatterns = get_health_urls()
