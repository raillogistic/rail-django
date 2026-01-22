"""
Binary custom scalar.
"""

import base64
import binascii
import hashlib
from pathlib import Path
from typing import Any, Optional, Union

from django.conf import settings
from graphene import Scalar
from graphql.error import GraphQLError
from graphql.language import ast

from .ast_utils import _STRING_VALUE_TYPES


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
