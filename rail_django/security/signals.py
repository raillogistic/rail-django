"""
Signal hooks for security-related cache invalidation.
"""

import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed

from .rbac import role_manager

logger = logging.getLogger(__name__)

_signals_connected = False


def connect_permission_cache_signals() -> None:
    global _signals_connected
    if _signals_connected:
        return

    try:
        user_model = get_user_model()
    except Exception as exc:
        logger.warning("Failed to load user model for permission cache signals: %s", exc)
        return

    try:
        m2m_changed.connect(
            _user_groups_changed, sender=user_model.groups.through
        )
    except Exception as exc:
        logger.warning("Failed to connect group membership signals: %s", exc)

    try:
        m2m_changed.connect(
            _user_permissions_changed, sender=user_model.user_permissions.through
        )
    except Exception as exc:
        logger.warning("Failed to connect user permission signals: %s", exc)

    try:
        from django.contrib.auth.models import Group

        m2m_changed.connect(
            _group_permissions_changed, sender=Group.permissions.through
        )
    except Exception as exc:
        logger.debug("Group permission signals unavailable: %s", exc)

    _signals_connected = True


def _user_groups_changed(sender, instance, action, **kwargs) -> None:
    if action in {"post_add", "post_remove", "post_clear"}:
        role_manager.invalidate_user_cache(instance)


def _user_permissions_changed(sender, instance, action, **kwargs) -> None:
    if action in {"post_add", "post_remove", "post_clear"}:
        role_manager.invalidate_user_cache(instance)


def _group_permissions_changed(sender, instance, action, **kwargs) -> None:
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    try:
        users = list(instance.user_set.all())
    except Exception:
        return
    for user in users:
        role_manager.invalidate_user_cache(user)
