from django.apps import AppConfig
from django.db.models.signals import post_migrate


class SecurityConfig(AppConfig):
    name = "rail_django.security"
    verbose_name = "Rail Django Security"

    def ready(self):
        # Import to register signal handlers
        from . import signals  # noqa
        try:
            signals.connect_permission_cache_signals()
        except Exception:
            # Keep startup resilient when auth models aren't fully ready.
            pass
        post_migrate.connect(
            _sync_roles_to_groups,
            dispatch_uid="rail_django.security.sync_roles_to_groups",
        )

        # Initialize event bus (lazy, only creates when first event emitted)
        # The bus auto-starts in get_event_bus()


def _sync_roles_to_groups(**kwargs):
    try:
        from .rbac import role_manager

        role_manager.sync_roles_to_groups()
    except Exception:
        # Keep startup and migrations resilient.
        return
