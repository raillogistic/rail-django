import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


class AppConfig(AppConfig):
    name = "rail_django"
    verbose_name = "Rail Django"

    def ready(self) -> None:
        mode = getattr(settings, "RAIL_METADATA_DEPLOY_VERSION", {}).get(
            "mode", "command"
        )

        if mode == "migration":
            post_migrate.connect(_bump_on_migrate, sender=self)
        elif mode == "startup":
            try:
                from rail_django.extensions.metadata.deploy_version import (
                    bump_deploy_version,
                )

                bump_deploy_version()
                logger.info("Metadata deploy version bumped on startup.")
            except Exception as exc:
                logger.warning(
                    "Failed to bump metadata deploy version on startup: %s", exc
                )


def _bump_on_migrate(**kwargs) -> None:
    try:
        from rail_django.extensions.metadata.deploy_version import bump_deploy_version

        bump_deploy_version()
        logger.info("Metadata deploy version bumped after migrations.")
    except Exception as exc:
        logger.warning("Failed to bump metadata deploy version on migrate: %s", exc)
