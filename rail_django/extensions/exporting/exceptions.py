"""Export Exceptions

This module defines exception classes used throughout the exporting package.
"""


class ExportError(Exception):
    """Custom exception for export-related errors.

    This exception is raised when export operations fail due to
    validation errors, permission issues, or processing failures.
    """

    pass
