"""
AuditLogger implementation.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.extensions.audit.logger` package.

DEPRECATION NOTICE:
    Importing from `rail_django.extensions.audit.logger` is deprecated.
    Please update your imports to use `rail_django.extensions.audit.logger` package instead.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.extensions.audit.logger' module is deprecated. "
    "Use 'rail_django.extensions.audit.logger' package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .logger.base import AuditLogger
from .logger.loggers import (
    log_audit_event,
    log_authentication_event,
    audit_logger,
)
from .logger.utils import get_security_dashboard_data

__all__ = [
    "AuditLogger",
    "log_audit_event",
    "log_authentication_event",
    "audit_logger",
    "get_security_dashboard_data",
]