"""
Form API configuration settings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormSettings:
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600
