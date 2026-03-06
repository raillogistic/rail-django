"""
Compatibility shim for the removed app-level GraphQLMeta file loader.

GraphQLMeta must now be declared directly on the Django model class.
"""

from __future__ import annotations

from typing import Iterable, Optional


def load_app_meta_configs(
    app_configs: Optional[Iterable[object]] = None,
) -> int:
    """Legacy no-op kept for import compatibility."""
    del app_configs
    return 0


def get_model_meta_config(model_class: object) -> Optional[object]:
    """Legacy no-op kept for import compatibility."""
    del model_class
    return None


def clear_meta_configs() -> None:
    """Legacy no-op kept for import compatibility."""
    return None
