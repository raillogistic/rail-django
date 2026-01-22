"""
Management command for health monitoring.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.management.commands.health_monitor` package.
"""

from .health_monitor.command import Command

__all__ = ["Command"]