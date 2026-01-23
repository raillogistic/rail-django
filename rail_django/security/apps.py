from django.apps import AppConfig


class SecurityConfig(AppConfig):
    name = "rail_django.security"
    verbose_name = "Rail Django Security"

    def ready(self):
        # Import to register signal handlers
        from . import signals  # noqa

        # Initialize event bus (lazy, only creates when first event emitted)
        # The bus auto-starts in get_event_bus()
