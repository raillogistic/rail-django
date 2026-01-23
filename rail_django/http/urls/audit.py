"""
URL patterns for audit and security monitoring endpoints.
"""

from ..views.audit import get_audit_urls

audit_urlpatterns = get_audit_urls()
