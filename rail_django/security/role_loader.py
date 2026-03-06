"""
Compatibility shim for the removed app-level role file loader.
"""

from __future__ import annotations

from typing import Iterable, Optional


def load_app_role_definitions(
    app_configs: Optional[Iterable[object]] = None,
) -> int:
    """Legacy no-op kept for import compatibility."""
    del app_configs
    return 0
