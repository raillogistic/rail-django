"""
URL patterns for audit and security monitoring endpoints.
"""

from .views.audit_views import get_audit_urls

audit_urlpatterns = get_audit_urls()
