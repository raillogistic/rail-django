"""
Debug hooks module.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.debugging.debug_hooks` package.

DEPRECATION NOTICE:
    Importing from `rail_django.debugging.debug_hooks` module is deprecated.
    Please update your imports to use `rail_django.debugging.debug_hooks` package instead.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.debugging.debug_hooks' module is deprecated. "
    "Use 'rail_django.debugging.debug_hooks' package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .debug_hooks.hooks import DebugHooks
from .debug_hooks.types import DebugEvent, DebugLevel, DebugSession

__all__ = [
    "DebugHooks",
    "DebugLevel",
    "DebugEvent",
    "DebugSession",
]