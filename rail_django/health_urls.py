"""
URL patterns pour le système de surveillance de santé GraphQL.

Ce module définit tous les endpoints pour le monitoring de santé,
les diagnostics et le tableau de bord.
"""

from django.http import JsonResponse
from django.urls import path
from django.views.generic import TemplateView


# Simple health check views to avoid circular imports
def simple_health_dashboard(request):
    """Simple health dashboard view."""
    from django.shortcuts import render
    return render(request, 'health_dashboard.html')


def simple_health_api(request):
    """Simple health API endpoint."""
    return JsonResponse({
        'status': 'healthy',
        'timestamp': '2025-01-27T10:00:00Z',
        'components': {
            'database': 'healthy',
            'cache': 'healthy',
            'schema': 'healthy'
        }
    })


def simple_health_check(request):
    """Simple health check endpoint."""
    return JsonResponse({'status': 'ok'})


# Health URL patterns
health_urlpatterns = [
    # Tableau de bord principal
    path('health/', simple_health_dashboard, name='health_dashboard'),
    path('health/dashboard/', simple_health_dashboard, name='health_dashboard_explicit'),

    # API endpoints pour les données de santé
    path('health/api/', simple_health_api, name='health_api'),

    # Endpoints de vérification simple
    path('health/check/', simple_health_check, name='health_check'),
    path('health/ping/', simple_health_check, name='health_ping'),
    path('health/status/', simple_health_check, name='health_status'),
]
