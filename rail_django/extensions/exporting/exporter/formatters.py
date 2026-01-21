"""Field Formatting Utilities

This module provides field value formatting and sanitization utilities
for the exporting package.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for older Python
    ZoneInfo = None

from django.db import models
from django.utils import formats, timezone

from ..config import FORMULA_PREFIXES, normalize_accessor_value


class FieldFormatter:
    """Handles field value formatting for export."""

    def __init__(
        self,
        *,
        sanitize_formulas: bool = True,
        formula_escape_strategy: str = "prefix",
        formula_escape_prefix: str = "'",
        field_formatters: Optional[dict[str, Any]] = None,
    ):
        """Initialize the field formatter.

        Args:
            sanitize_formulas: Whether to escape formula-like values.
            formula_escape_strategy: Strategy for escaping formulas ('prefix' or 'tab').
            formula_escape_prefix: Character to prefix formula values.
            field_formatters: Dictionary of field-specific formatter configurations.
        """
        self.sanitize_formulas = sanitize_formulas
        self.formula_escape_strategy = formula_escape_strategy.lower()
        self.formula_escape_prefix = formula_escape_prefix
        self.field_formatters = field_formatters or {}

    def format_value(self, value: Any) -> Any:
        """Format value for export based on its type.

        Args:
            value: The value to format.

        Returns:
            Formatted value suitable for export.
        """
        if value is None:
            return ""
        if isinstance(value, bool):
            formatted: Any = "Yes" if value else "No"
        elif isinstance(value, (datetime, date)):
            if isinstance(value, datetime):
                # Convert timezone-aware datetime to local time
                if timezone.is_aware(value):
                    value = timezone.localtime(value)
                formatted = value.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted = value.strftime("%Y-%m-%d")
        elif isinstance(value, Decimal):
            formatted = float(value)
        elif isinstance(value, models.Model):
            # For related objects, return string representation
            formatted = str(value)
        elif hasattr(value, "all"):
            # For many-to-many fields, join related objects
            formatted = ", ".join(str(item) for item in value.all())
        else:
            formatted = str(value)

        if isinstance(formatted, str):
            return self.sanitize_formula_value(formatted)
        return formatted

    def sanitize_formula_value(self, value: str) -> str:
        """Escape values that could be interpreted as formulas by spreadsheet tools.

        This prevents formula injection attacks in CSV and Excel exports.

        Args:
            value: String value to sanitize.

        Returns:
            Sanitized string value.
        """
        if not self.sanitize_formulas or not value:
            return value
        stripped = value.lstrip()
        if stripped and stripped[0] in FORMULA_PREFIXES:
            if self.formula_escape_strategy == "prefix":
                return f"{self.formula_escape_prefix}{value}"
            if self.formula_escape_strategy == "tab":
                return f"\t{value}"
        return value

    def apply_field_formatter(self, value: Any, accessor: str) -> Any:
        """Apply per-field formatting or masking.

        Args:
            value: The value to format.
            accessor: The field accessor path.

        Returns:
            Formatted value based on field-specific configuration.
        """
        formatter = self.field_formatters.get(normalize_accessor_value(accessor))
        if not formatter:
            return value
        if isinstance(formatter, str):
            formatter = {"type": formatter}

        formatter_type = str(formatter.get("type", "")).lower()
        if formatter_type == "redact":
            return formatter.get("value", "[REDACTED]")
        if formatter_type == "mask":
            raw = "" if value is None else str(value)
            show_last = int(formatter.get("show_last", 4))
            mask_char = str(formatter.get("mask_char", "*"))
            if show_last <= 0:
                return mask_char * len(raw)
            masked = mask_char * max(len(raw) - show_last, 0)
            return f"{masked}{raw[-show_last:]}" if raw else raw
        if formatter_type in {"datetime", "date"}:
            if not isinstance(value, (datetime, date)):
                return value
            tz_name = formatter.get("timezone")
            if isinstance(value, datetime):
                if timezone.is_naive(value):
                    value = timezone.make_aware(value, timezone.get_default_timezone())
                if tz_name and ZoneInfo:
                    try:
                        value = value.astimezone(ZoneInfo(str(tz_name)))
                    except Exception:
                        pass
                else:
                    value = timezone.localtime(value)
            format_value = formatter.get("format")
            if format_value:
                return formats.date_format(value, format_value)
            return formats.date_format(
                value,
                "DATETIME_FORMAT" if isinstance(value, datetime) else "DATE_FORMAT",
            )
        if formatter_type == "number":
            if not isinstance(value, (int, float, Decimal)):
                return value
            decimal_pos = formatter.get("decimal_pos", None)
            use_l10n = bool(formatter.get("use_l10n", True))
            return formats.number_format(
                value, decimal_pos=decimal_pos, use_l10n=use_l10n
            )
        return value
