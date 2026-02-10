"""Domain exceptions for import services."""

from __future__ import annotations


class ImportServiceError(Exception):
    """Typed error used by import services to provide issue code and context."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        row_number: int | None = None,
        field_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.row_number = row_number
        self.field_path = field_path

