"""
Common custom scalars (UUID, Email, URL, Phone, Decimal).
"""

import re
import uuid
from decimal import Decimal as DecimalType
from typing import Union
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from graphene import Scalar
from graphql.error import GraphQLError
from graphql.language import ast

from .ast_utils import (
    _FLOAT_VALUE_TYPES,
    _INT_VALUE_TYPES,
    _STRING_VALUE_TYPES,
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
