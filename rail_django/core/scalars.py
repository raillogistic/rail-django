"""
Custom GraphQL scalars for Rail Django GraphQL.

This module implements custom scalar types defined in LIBRARY_DEFAULTS
including DateTime, Date, Time, JSON, UUID, Email, URL, and Phone scalars.
"""

import base64
import binascii
import hashlib
import json
import re
import uuid
from datetime import date, datetime, time
from decimal import Decimal as DecimalType
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import urlparse

import graphene
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from graphene import Scalar
from graphql.error import GraphQLError
from graphql.language import ast

from ..config_proxy import get_setting

_AST_STRING_VALUE = getattr(ast, "StringValue", None)
_AST_STRING_VALUE_NODE = getattr(ast, "StringValueNode", None)
_AST_OBJECT_VALUE = getattr(ast, "ObjectValue", None)
_AST_OBJECT_VALUE_NODE = getattr(ast, "ObjectValueNode", None)
_AST_LIST_VALUE = getattr(ast, "ListValue", None)
_AST_LIST_VALUE_NODE = getattr(ast, "ListValueNode", None)
_AST_BOOLEAN_VALUE = getattr(ast, "BooleanValue", None)
_AST_BOOLEAN_VALUE_NODE = getattr(ast, "BooleanValueNode", None)
_AST_INT_VALUE = getattr(ast, "IntValue", None)
_AST_INT_VALUE_NODE = getattr(ast, "IntValueNode", None)
_AST_FLOAT_VALUE = getattr(ast, "FloatValue", None)
_AST_FLOAT_VALUE_NODE = getattr(ast, "FloatValueNode", None)
_AST_NULL_VALUE = getattr(ast, "NullValue", None)
_AST_NULL_VALUE_NODE = getattr(ast, "NullValueNode", None)

_STRING_VALUE_TYPES = tuple(
    t for t in (_AST_STRING_VALUE, _AST_STRING_VALUE_NODE) if t
)
_OBJECT_VALUE_TYPES = tuple(
    t for t in (_AST_OBJECT_VALUE, _AST_OBJECT_VALUE_NODE) if t
)
_LIST_VALUE_TYPES = tuple(
    t for t in (_AST_LIST_VALUE, _AST_LIST_VALUE_NODE) if t
)
_BOOLEAN_VALUE_TYPES = tuple(
    t for t in (_AST_BOOLEAN_VALUE, _AST_BOOLEAN_VALUE_NODE) if t
)
_INT_VALUE_TYPES = tuple(
    t for t in (_AST_INT_VALUE, _AST_INT_VALUE_NODE) if t
)
_FLOAT_VALUE_TYPES = tuple(
    t for t in (_AST_FLOAT_VALUE, _AST_FLOAT_VALUE_NODE) if t
)
_NULL_VALUE_TYPES = tuple(
    t for t in (_AST_NULL_VALUE, _AST_NULL_VALUE_NODE) if t
)

try:
    from graphene.types.decimal import Decimal as GrapheneDecimal
except Exception:
    GrapheneDecimal = None

if GrapheneDecimal is not None:
    _graphene_decimal_parse_literal = GrapheneDecimal.parse_literal

    def _patched_graphene_decimal_parse_literal(cls, node, _variables=None):
        if _FLOAT_VALUE_TYPES and isinstance(node, _FLOAT_VALUE_TYPES):
            return cls.parse_value(node.value)
        return _graphene_decimal_parse_literal(node, _variables)

    GrapheneDecimal.parse_literal = classmethod(
        _patched_graphene_decimal_parse_literal
    )

class DateTime(Scalar):
    """
    Custom DateTime scalar that handles timezone-aware datetime objects.

    Serializes datetime objects to ISO 8601 format strings.
    Parses ISO 8601 format strings to datetime objects.
    """

    @staticmethod
    def serialize(dt: datetime) -> str:
        """Serialize datetime to ISO 8601 string."""
        if not isinstance(dt, datetime):
            raise GraphQLError(f"Value must be a datetime object, got {type(dt).__name__}")

        # Ensure timezone awareness
        if dt.tzinfo is None:
            dt = timezone.make_aware(dt)

        return dt.isoformat()

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> datetime:
        """Parse AST literal to datetime."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return DateTime.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as DateTime")

    @staticmethod
    def parse_value(value: str) -> datetime:
        """Parse string value to datetime."""
        if not isinstance(value, str):
            raise GraphQLError(f"DateTime must be a string, got {type(value).__name__}")

        try:
            dt = parse_datetime(value)
            if dt is None:
                # Try parsing with different formats
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))

            # Ensure timezone awareness
            if dt.tzinfo is None:
                dt = timezone.make_aware(dt)

            return dt
        except (ValueError, TypeError) as e:
            raise GraphQLError(f"Invalid DateTime format: {e}")


class Date(Scalar):
    """
    Custom Date scalar that handles date objects.

    Serializes date objects to ISO format strings (YYYY-MM-DD).
    Parses ISO format strings to date objects.
    """

    @staticmethod
    def serialize(d: date) -> str:
        """Serialize date to ISO string."""
        if not isinstance(d, date):
            raise GraphQLError(f"Value must be a date object, got {type(d).__name__}")

        return d.isoformat()

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> date:
        """Parse AST literal to date."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return Date.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as Date")

    @staticmethod
    def parse_value(value: str) -> date:
        """Parse string value to date."""
        if not isinstance(value, str):
            raise GraphQLError(f"Date must be a string, got {type(value).__name__}")

        try:
            d = parse_date(value)
            if d is None:
                d = datetime.fromisoformat(value).date()

            return d
        except (ValueError, TypeError) as e:
            raise GraphQLError(f"Invalid Date format: {e}")


class Time(Scalar):
    """
    Custom Time scalar that handles time objects.

    Serializes time objects to ISO format strings (HH:MM:SS).
    Parses ISO format strings to time objects.
    """

    @staticmethod
    def serialize(t: time) -> str:
        """Serialize time to ISO string."""
        if not isinstance(t, time):
            raise GraphQLError(f"Value must be a time object, got {type(t).__name__}")

        return t.isoformat()

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> time:
        """Parse AST literal to time."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return Time.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as Time")

    @staticmethod
    def parse_value(value: str) -> time:
        """Parse string value to time."""
        if not isinstance(value, str):
            raise GraphQLError(f"Time must be a string, got {type(value).__name__}")

        try:
            t = parse_time(value)
            if t is None:
                t = datetime.fromisoformat(f"2000-01-01T{value}").time()

            return t
        except (ValueError, TypeError) as e:
            raise GraphQLError(f"Invalid Time format: {e}")


class JSON(Scalar):
    """
    Custom JSON scalar that handles JSON data.

    Serializes Python objects to JSON strings.
    Parses JSON strings to Python objects.
    """

    @staticmethod
    def serialize(value: Any) -> str:
        """Serialize Python object to JSON string."""
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError) as e:
            raise GraphQLError(f"Cannot serialize value as JSON: {e}")

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> Any:
        """Parse AST literal to Python object."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return JSON.parse_value(node.value)
        elif _OBJECT_VALUE_TYPES and isinstance(node, _OBJECT_VALUE_TYPES):
            return {field.name.value: JSON.parse_literal(field.value) for field in node.fields}
        elif _LIST_VALUE_TYPES and isinstance(node, _LIST_VALUE_TYPES):
            return [JSON.parse_literal(value) for value in node.values]
        elif _BOOLEAN_VALUE_TYPES and isinstance(node, _BOOLEAN_VALUE_TYPES):
            return node.value
        elif _INT_VALUE_TYPES and isinstance(node, _INT_VALUE_TYPES):
            return int(node.value)
        elif _FLOAT_VALUE_TYPES and isinstance(node, _FLOAT_VALUE_TYPES):
            return float(node.value)
        elif _NULL_VALUE_TYPES and isinstance(node, _NULL_VALUE_TYPES):
            return None

        raise GraphQLError(f"Cannot parse {type(node).__name__} as JSON")

    @staticmethod
    def parse_value(value: Union[str, dict, list]) -> Any:
        """Parse value to Python object."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError) as e:
                raise GraphQLError(f"Invalid JSON format: {e}")

        return value


class UUID(Scalar):
    """
    Custom UUID scalar that handles UUID objects.

    Serializes UUID objects to string representation.
    Parses string UUIDs to UUID objects.
    """

    @staticmethod
    def serialize(value: uuid.UUID) -> str:
        """Serialize UUID to string."""
        if not isinstance(value, uuid.UUID):
            raise GraphQLError(f"Value must be a UUID object, got {type(value).__name__}")

        return str(value)

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> uuid.UUID:
        """Parse AST literal to UUID."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return UUID.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as UUID")

    @staticmethod
    def parse_value(value: str) -> uuid.UUID:
        """Parse string value to UUID."""
        if not isinstance(value, str):
            raise GraphQLError(f"UUID must be a string, got {type(value).__name__}")

        try:
            return uuid.UUID(value)
        except (ValueError, TypeError) as e:
            raise GraphQLError(f"Invalid UUID format: {e}")


class Email(Scalar):
    """
    Custom Email scalar that validates email addresses.

    Uses Django's email validation.
    """

    @staticmethod
    def serialize(value: str) -> str:
        """Serialize email string."""
        if not isinstance(value, str):
            raise GraphQLError(f"Email must be a string, got {type(value).__name__}")

        # Validate email format
        try:
            validate_email(value)
        except ValidationError as e:
            raise GraphQLError(f"Invalid email format: {e}")

        return value

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> str:
        """Parse AST literal to email string."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return Email.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as Email")

    @staticmethod
    def parse_value(value: str) -> str:
        """Parse and validate email string."""
        if not isinstance(value, str):
            raise GraphQLError(f"Email must be a string, got {type(value).__name__}")

        try:
            validate_email(value)
        except ValidationError as e:
            raise GraphQLError(f"Invalid email format: {e}")

        return value


class URL(Scalar):
    """
    Custom URL scalar that validates URLs.

    Validates URL format and scheme.
    """

    @staticmethod
    def serialize(value: str) -> str:
        """Serialize URL string."""
        if not isinstance(value, str):
            raise GraphQLError(f"URL must be a string, got {type(value).__name__}")

        # Validate URL format
        URL._validate_url(value)
        return value

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> str:
        """Parse AST literal to URL string."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return URL.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as URL")

    @staticmethod
    def parse_value(value: str) -> str:
        """Parse and validate URL string."""
        if not isinstance(value, str):
            raise GraphQLError(f"URL must be a string, got {type(value).__name__}")

        URL._validate_url(value)
        return value

    @staticmethod
    def _validate_url(url: str) -> None:
        """Validate URL format."""
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise GraphQLError("URL must have scheme and netloc")

            if parsed.scheme not in ['http', 'https', 'ftp', 'ftps']:
                raise GraphQLError(f"Unsupported URL scheme: {parsed.scheme}")

        except Exception as e:
            raise GraphQLError(f"Invalid URL format: {e}")


class Phone(Scalar):
    """
    Custom Phone scalar that validates phone numbers.

    Basic phone number validation with international format support.
    """

    # Basic phone number regex (can be enhanced)
    PHONE_REGEX = re.compile(r'^\+?[1-9]\d{1,14}$')

    @staticmethod
    def serialize(value: str) -> str:
        """Serialize phone string."""
        if not isinstance(value, str):
            raise GraphQLError(f"Phone must be a string, got {type(value).__name__}")

        # Validate phone format
        Phone._validate_phone(value)
        return value

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> str:
        """Parse AST literal to phone string."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return Phone.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as Phone")

    @staticmethod
    def parse_value(value: str) -> str:
        """Parse and validate phone string."""
        if not isinstance(value, str):
            raise GraphQLError(f"Phone must be a string, got {type(value).__name__}")

        Phone._validate_phone(value)
        return value

    @staticmethod
    def _validate_phone(phone: str) -> None:
        """Validate phone number format."""
        # Remove common separators for validation
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)

        if not Phone.PHONE_REGEX.match(cleaned):
            raise GraphQLError("Invalid phone number format")


class Decimal(Scalar):
    """
    Custom Decimal scalar for precise decimal arithmetic.

    Handles Python Decimal objects for financial calculations.
    """

    @staticmethod
    def serialize(value: DecimalType) -> str:
        """Serialize Decimal to string."""
        if not isinstance(value, DecimalType):
            raise GraphQLError(f"Value must be a Decimal object, got {type(value).__name__}")

        return str(value)

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> DecimalType:
        """Parse AST literal to Decimal."""
        if (
            (_STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES))
            or (_INT_VALUE_TYPES and isinstance(node, _INT_VALUE_TYPES))
            or (_FLOAT_VALUE_TYPES and isinstance(node, _FLOAT_VALUE_TYPES))
        ):
            return Decimal.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as Decimal")

    @staticmethod
    def parse_value(value: Union[str, int, float]) -> DecimalType:
        """Parse value to Decimal."""
        try:
            return DecimalType(str(value))
        except (ValueError, TypeError) as e:
            raise GraphQLError(f"Invalid Decimal format: {e}")


class Binary(Scalar):
    """Binary scalar that stores binary payloads under MEDIA_ROOT and returns URLs."""

    STORAGE_SUBDIR = "binary-fields"

    @staticmethod
    def _ensure_dir() -> Path:
        media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
        target_dir = media_root / Binary.STORAGE_SUBDIR
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    @staticmethod
    def _build_url(filename: str) -> str:
        media_url = getattr(settings, "MEDIA_URL", "/media/")
        media_url = media_url if media_url.endswith("/") else f"{media_url}/"
        relative_path = f"{Binary.STORAGE_SUBDIR}/{filename}"
        return f"{media_url}{relative_path}"

    @staticmethod
    def serialize(value: Any) -> Optional[str]:
        if value is None:
            return None

        if isinstance(value, memoryview):
            value = value.tobytes()
        elif isinstance(value, bytearray):
            value = bytes(value)

        if not isinstance(value, (bytes, bytearray)):
            raise GraphQLError(
                f"Binary field must serialize from bytes, got {type(value).__name__}"
            )

        data = bytes(value)
        target_dir = Binary._ensure_dir()
        digest = hashlib.sha256(data).hexdigest()
        filename = f"{digest}.bin"
        file_path = target_dir / filename
        if not file_path.exists():
            file_path.write_bytes(data)

        return Binary._build_url(filename)

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> Optional[bytes]:
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return Binary.parse_value(node.value)
        raise GraphQLError(f"Cannot parse {type(node).__name__} as Binary")

    @staticmethod
    def parse_value(value: Union[str, bytes, bytearray, memoryview]) -> Optional[bytes]:
        if value is None:
            return None

        if isinstance(value, memoryview):
            return value.tobytes()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if not isinstance(value, str):
            raise GraphQLError(
                f"Binary input must be a base64 string, got {type(value).__name__}"
            )

        try:
            return base64.b64decode(value)
        except (binascii.Error, ValueError) as exc:
            raise GraphQLError(f"Invalid base64 payload for Binary field: {exc}")


# Registry of custom scalars
CUSTOM_SCALARS = {
    'DateTime': DateTime,
    'Date': Date,
    'Time': Time,
    'JSON': JSON,
    'UUID': UUID,
    'Email': Email,
    'URL': URL,
    'Phone': Phone,
    'Decimal': Decimal,
    'Binary': Binary,
}


def get_custom_scalar(scalar_name: str) -> Optional[type]:
    """
    Get custom scalar class by name.

    Args:
        scalar_name: Name of the scalar

    Returns:
        Scalar class or None if not found
    """
    return CUSTOM_SCALARS.get(scalar_name)


def register_custom_scalar(name: str, scalar_class: type) -> None:
    """
    Register a custom scalar.

    Args:
        name: Name of the scalar
        scalar_class: Scalar class
    """
    CUSTOM_SCALARS[name] = scalar_class


def get_enabled_scalars(schema_name: Optional[str] = None) -> dict:
    """
    Get enabled custom scalars for a schema.

    Args:
        schema_name: Schema name (optional)

    Returns:
        Dictionary of enabled scalars
    """
    from ..defaults import LIBRARY_DEFAULTS

    # Get custom scalars configuration
    custom_scalars_config = LIBRARY_DEFAULTS.get("custom_scalars", {})

    enabled_scalars = {}
    for scalar_name, config in custom_scalars_config.items():
        if isinstance(config, dict) and config.get("enabled", True):
            scalar_class = get_custom_scalar(scalar_name)
            if scalar_class:
                enabled_scalars[scalar_name] = scalar_class

    return enabled_scalars
