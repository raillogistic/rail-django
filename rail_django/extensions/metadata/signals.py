"""Signal handlers for metadata cache invalidation.

This module provides Django signal handlers that automatically invalidate
the metadata cache when model structure changes occur. Cache invalidation
is conservative and only triggers during migrations or when model structure
actually changes, not during regular data operations.
"""

import logging
import sys
from typing import Any, Optional

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_metadata_cache

logger = logging.getLogger(__name__)

# Migration context detection cache
_migration_context_cache: Optional[bool] = None


def _is_in_migration_context() -> bool:
    """Check if we're currently in a Django migration context.

    Detects if the current process is running migration-related
    commands by checking sys.argv for migration command names.

    Returns:
        bool: True if running migrate, makemigrations, or showmigrations.

    Example:
        >>> # When running: python manage.py migrate
        >>> _is_in_migration_context()
        True
    """
    global _migration_context_cache
    if _migration_context_cache is not None:
        return _migration_context_cache

    migration_commands = {"migrate", "makemigrations", "showmigrations"}
    if any(cmd in sys.argv for cmd in migration_commands):
        _migration_context_cache = True
        return True

    _migration_context_cache = False
    return False


def _is_model_structure_change(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any,
) -> bool:
    """Determine if this is a model structure change vs regular data operation.

    Model structure changes include:
    - Running migrations
    - Changes to Django internal models (contenttypes, auth, admin)
    - Models with custom metadata flags indicating schema impact

    Regular data operations (CRUD on user data) do not trigger cache
    invalidation for performance reasons.

    Args:
        sender: The model class that triggered the signal.
        instance: The model instance being saved.
        created: Whether this is a new instance (True) or update (False).
        **kwargs: Additional signal arguments.

    Returns:
        bool: True if this is likely a structure change requiring cache invalidation.

    Example:
        >>> from django.contrib.auth.models import User
        >>> # Regular user creation - not a structure change
        >>> _is_model_structure_change(User, user_instance, True)
        False
    """
    # Check if we're in a migration context
    if _is_in_migration_context():
        return True

    # Check if this is a Django internal model that affects schema
    if sender._meta.app_label in ["contenttypes", "auth", "admin"]:
        # These apps can affect GraphQL schema structure
        return True

    # Check if this model has custom metadata that might affect schema
    if hasattr(sender, "_graphql_metadata_affects_schema"):
        return getattr(sender, "_graphql_metadata_affects_schema", False)

    # For now, be conservative and don't invalidate on regular data operations
    return False


def _is_m2m_structure_change(
    sender: Any,
    action: str,
    **kwargs: Any,
) -> bool:
    """Determine if this is an M2M structure change vs regular data operation.

    Many-to-many relationship changes only trigger cache invalidation
    during migrations, not during regular data operations.

    Args:
        sender: The through model for the many-to-many field.
        action: The type of M2M change (post_add, post_remove, post_clear).
        **kwargs: Additional signal arguments.

    Returns:
        bool: True if this is likely a structure change requiring cache invalidation.

    Example:
        >>> # Regular M2M add during normal operation
        >>> _is_m2m_structure_change(ThroughModel, "post_add")
        False
    """
    # Check if we're in a migration context
    if _is_in_migration_context():
        return True

    # For now, be conservative and don't invalidate on regular M2M operations
    return False


def reset_migration_context_cache() -> None:
    """Reset the migration context detection cache.

    Useful for testing scenarios where the migration context
    needs to be re-evaluated.

    Example:
        >>> reset_migration_context_cache()
        >>> _is_in_migration_context()  # Will re-check sys.argv
    """
    global _migration_context_cache
    _migration_context_cache = None


@receiver(post_save, sender=None)
def invalidate_model_metadata_cache_on_save(
    sender: Any,
    instance: Any,
    created: bool,
    **kwargs: Any,
) -> None:
    """Invalidate metadata cache only when model structure changes.

    This signal handler is triggered on every model save but only
    performs cache invalidation when:
    - New models are created (migrations)
    - Model fields are added/removed (migrations)
    - Model relationships change (migrations)

    Regular data operations (creating users, products, etc.) do not
    trigger cache invalidation for performance reasons.

    Args:
        sender: The model class that was saved.
        instance: The model instance that was saved.
        created: Whether this is a new instance (True) or update (False).
        **kwargs: Additional signal arguments.

    Example:
        >>> # This is automatically connected via Django signals
        >>> # When a migration runs, the cache is invalidated
    """
    # Only invalidate cache for model structure changes, not data changes
    if sender and hasattr(sender, "_meta"):
        # Skip cache invalidation for regular data operations
        # Only invalidate during migrations or when model structure changes
        if _is_model_structure_change(sender, instance, created, **kwargs):
            app_name = sender._meta.app_label
            model_name = sender.__name__

            # Invalidate cache for this specific model
            invalidate_metadata_cache(model_name=model_name, app_name=app_name)
            logger.info(
                "Invalidated metadata cache for %s.%s due to model structure change",
                app_name,
                model_name,
            )


@receiver(post_delete, sender=None)
def invalidate_model_metadata_cache_on_delete(
    sender: Any,
    instance: Any,
    **kwargs: Any,
) -> None:
    """Invalidate metadata cache when models are deleted structurally.

    This is more conservative and only invalidates when it's likely
    a model structure change rather than regular data deletion.

    Args:
        sender: The model class that was deleted.
        instance: The model instance that was deleted.
        **kwargs: Additional signal arguments.

    Example:
        >>> # This is automatically connected via Django signals
        >>> # Cache only invalidated during migrations, not regular deletes
    """
    if sender and hasattr(sender, "_meta"):
        # Only invalidate for structural changes, not regular deletions
        if _is_model_structure_change(sender, instance, False, **kwargs):
            app_name = sender._meta.app_label
            model_name = sender.__name__

            # Invalidate cache for this specific model
            invalidate_metadata_cache(model_name=model_name, app_name=app_name)
            logger.info(
                "Invalidated metadata cache for %s.%s due to model deletion",
                app_name,
                model_name,
            )


@receiver(m2m_changed)
def invalidate_m2m_metadata_cache(
    sender: Any,
    action: str,
    **kwargs: Any,
) -> None:
    """Invalidate metadata cache when many-to-many relationships change structurally.

    Only invalidates on structural changes (during migrations),
    not regular data changes (adding/removing M2M relationships).

    Args:
        sender: The through model for the M2M field.
        action: The type of M2M change (post_add, post_remove, post_clear).
        **kwargs: Additional signal arguments.

    Example:
        >>> # This is automatically connected via Django signals
        >>> # Only migration-time M2M changes trigger invalidation
    """
    # Only invalidate on structural changes, not data operations
    if (
        action in ["post_add", "post_remove", "post_clear"]
        and sender
        and hasattr(sender, "_meta")
    ):
        # Check if this is a structural change vs data change
        if _is_m2m_structure_change(sender, action, **kwargs):
            app_name = sender._meta.app_label
            model_name = sender.__name__

            # Invalidate cache for this specific model
            invalidate_metadata_cache(model_name=model_name, app_name=app_name)
            logger.info(
                "Invalidated m2m metadata cache for %s.%s due to relationship structure change",
                app_name,
                model_name,
            )


__all__ = [
    "invalidate_model_metadata_cache_on_save",
    "invalidate_model_metadata_cache_on_delete",
    "invalidate_m2m_metadata_cache",
    "_is_model_structure_change",
    "_is_m2m_structure_change",
    "_is_in_migration_context",
    "reset_migration_context_cache",
]
