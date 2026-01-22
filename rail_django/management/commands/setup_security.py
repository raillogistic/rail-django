"""
Management command to setup security.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.management.commands.setup_security` package.
"""

from .setup_security.command import Command

__all__ = ["Command"]