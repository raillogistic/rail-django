"""
Canonical path helpers for generated form payloads and error mapping.
"""

from __future__ import annotations

from typing import Iterable

from ..config import DEFAULT_BULK_ROW_PATH_PREFIX, DEFAULT_FORM_ERROR_KEY


def normalize_path(path: str | None) -> str:
    if not path:
        return ""
    if str(path) == DEFAULT_FORM_ERROR_KEY:
        return DEFAULT_FORM_ERROR_KEY
    sentinel = "FORM_ERROR_KEY_SENTINEL"
    normalized = str(path).replace(DEFAULT_FORM_ERROR_KEY, sentinel)
    normalized = normalized.replace("__", ".")
    normalized = normalized.replace("[", ".").replace("]", "")
    while ".." in normalized:
        normalized = normalized.replace("..", ".")
    normalized = normalized.strip(".")
    return normalized.replace(sentinel, DEFAULT_FORM_ERROR_KEY)


def split_path(path: str | None) -> list[str]:
    normalized = normalize_path(path)
    return [part for part in normalized.split(".") if part] if normalized else []


def join_path(*segments: str | int | None) -> str:
    tokens: list[str] = []
    for segment in segments:
        if segment is None:
            continue
        token = normalize_path(str(segment))
        if token:
            tokens.extend(token.split("."))
    return ".".join(tokens)


def build_bulk_row_path(
    field: str | None,
    row_index: int | None,
    *,
    prefix: str = DEFAULT_BULK_ROW_PATH_PREFIX,
    form_key: str = DEFAULT_FORM_ERROR_KEY,
) -> str:
    field_path = (
        form_key if field in (None, "", DEFAULT_FORM_ERROR_KEY) else normalize_path(field)
    )
    field_path = field_path or form_key
    if row_index is None:
        return field_path
    return join_path(prefix, row_index, field_path)


def is_path_blocked(path: str, blocked_paths: Iterable[str]) -> bool:
    normalized = normalize_path(path)
    if not normalized:
        return False
    for blocked in blocked_paths:
        candidate = normalize_path(blocked)
        if not candidate:
            continue
        if normalized == candidate or normalized.startswith(f"{candidate}."):
            return True
    return False
