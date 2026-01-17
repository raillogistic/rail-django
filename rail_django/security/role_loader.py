"""
Role definition loader for meta.yaml/meta.json files.

This module is kept for backward compatibility with older imports. Roles are
now declared inside meta.yaml or meta.json and loaded by rail_django.core.meta_json.
"""

from __future__ import annotations

from typing import Iterable, Optional

from django.apps import apps

from ..core.meta_json import load_app_meta_configs


def load_app_role_definitions(
    app_configs: Optional[Iterable[object]] = None,
) -> int:
    """
    Load role definitions from meta.yaml or meta.json files.

    Args:
        app_configs: Optional iterable of Django app configs. Defaults to all
            installed apps.

    Returns:
        Number of model meta definitions registered.
    """
    if app_configs is None:
        app_configs = apps.get_app_configs()
    return load_app_meta_configs(app_configs)
