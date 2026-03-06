"""
Role definition loader for meta.json files.

Roles are declared inside meta.json and loaded by rail_django.core.meta.json_loader.
"""

from __future__ import annotations

from typing import Iterable, Optional

from django.apps import apps

from ..core.meta.json_loader import load_app_meta_configs


def load_app_role_definitions(
    app_configs: Optional[Iterable[object]] = None,
) -> int:
    """
    Load role definitions from meta.json files.

    Args:
        app_configs: Optional iterable of Django app configs. Defaults to all
            installed apps.

    Returns:
        Number of model meta definitions registered.
    """
    if app_configs is None:
        app_configs = apps.get_app_configs()
    return load_app_meta_configs(app_configs)
