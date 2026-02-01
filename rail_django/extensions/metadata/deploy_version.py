"""
Deployment-level metadata version helpers.
"""

import uuid
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError

from rail_django.models import MetadataDeployVersionModel


def _get_config() -> dict:
    return getattr(settings, "RAIL_METADATA_DEPLOY_VERSION", {}) or {}


def _get_key(config: Optional[dict] = None) -> str:
    cfg = config or _get_config()
    return str(cfg.get("key") or "default")


def _build_version_value() -> str:
    return uuid.uuid4().hex


def get_deploy_version(key: Optional[str] = None) -> str:
    version_key = key or _get_key()
    try:
        entry, _ = MetadataDeployVersionModel.objects.get_or_create(
            key=version_key,
            defaults={"version": _build_version_value()},
        )
        return entry.version
    except (OperationalError, ProgrammingError):
        return _build_version_value()


@transaction.atomic
def bump_deploy_version(key: Optional[str] = None, value: Optional[str] = None) -> str:
    version_key = key or _get_key()
    next_value = value or _build_version_value()
    try:
        entry, _ = (
            MetadataDeployVersionModel.objects.select_for_update().get_or_create(
                key=version_key,
                defaults={"version": next_value},
            )
        )
        if entry.version != next_value:
            entry.version = next_value
            entry.save(update_fields=["version", "updated_at"])
        return entry.version
    except (OperationalError, ProgrammingError):
        return next_value
