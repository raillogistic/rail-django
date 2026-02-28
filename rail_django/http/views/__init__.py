"""HTTP views for health, audit, CSRF, and scaffolded welcome endpoints."""

from .welcome import SuperuserRequiredTemplateView, WelcomeView

__all__ = ["SuperuserRequiredTemplateView", "WelcomeView"]
