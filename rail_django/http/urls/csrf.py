"""
URL patterns for CSRF bootstrap endpoint.
"""

from django.urls import path

from ..views.csrf import csrf_token_view

csrf_urlpatterns = [
    path("csrf/", csrf_token_view, name="csrf_token"),
]
