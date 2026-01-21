"""
Schema snapshot utilities for diffing and export endpoints.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

from django.apps import apps
from django.db.utils import OperationalError, ProgrammingError
from graphql.utilities import print_schema

from ..config_proxy import get_setting
from ..introspection.comparison.comparator import SchemaComparator
from ..introspection.schema_introspector import SchemaIntrospection, SchemaIntrospector

logger = logging.getLogger(__name__)


def snapshot_enabled(schema_name: Optional[str]) -> bool:
    return bool(get_setting("schema_registry.enable_schema_snapshots", False, schema_name))


def record_schema_snapshot(
    schema_name: str,
    schema: Any,
    *,
    version: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Any]:
    if not snapshot_enabled(schema_name):
        return None

    model = _get_snapshot_model()
    if model is None:
        return None

    schema_graphql = getattr(schema, "graphql_schema", None)
    if schema_graphql is None:
        return None

    try:
        sdl = print_schema(schema_graphql)
    except Exception:
        sdl = ""

    schema_hash = _hash_schema(sdl)
    resolved_version = str(version or getattr(schema, "version", "") or "")

    try:
        existing = model.objects.filter(
            schema_name=schema_name, version=resolved_version
        ).first()
        if existing and existing.schema_hash == schema_hash:
            return existing
    except (OperationalError, ProgrammingError):
        return None

    introspector = SchemaIntrospector()
    introspection = introspector.introspect_schema(
        schema_graphql, schema_name, version=resolved_version, description=description
    )

    try:
        snapshot = model.objects.create(
            schema_name=schema_name,
            version=resolved_version,
            schema_hash=schema_hash,
            schema_sdl=sdl,
            schema_json=introspection.to_dict(),
        )
    except (OperationalError, ProgrammingError):
        return None

    _prune_snapshots(schema_name, model)
    return snapshot


def list_schema_snapshots(
    schema_name: str, limit: int = 10
) -> list[Any]:
    model = _get_snapshot_model()
    if model is None:
        return []
    try:
        return list(model.objects.filter(schema_name=schema_name).order_by("-created_at")[:limit])
    except (OperationalError, ProgrammingError):
        return []


def get_schema_snapshot(
    schema_name: str, version: Optional[str] = None
) -> Optional[Any]:
    model = _get_snapshot_model()
    if model is None:
        return None
    try:
        if version is None:
            return model.objects.filter(schema_name=schema_name).order_by("-created_at").first()
        return model.objects.filter(schema_name=schema_name, version=version).first()
    except (OperationalError, ProgrammingError):
        return None


def get_schema_diff(
    from_snapshot: Any, to_snapshot: Any
) -> Optional[dict[str, Any]]:
    if not from_snapshot or not to_snapshot:
        return None
    try:
        old_intro = SchemaIntrospection.from_dict(from_snapshot.schema_json)
        new_intro = SchemaIntrospection.from_dict(to_snapshot.schema_json)
    except Exception:
        return None

    comparator = SchemaComparator()
    comparison = comparator.compare_schemas(old_intro, new_intro)
    return comparison.to_dict()


def _hash_schema(sdl: str) -> str:
    return hashlib.sha256((sdl or "").encode("utf-8")).hexdigest()


def _get_snapshot_model():
    try:
        return apps.get_model("rail_django", "SchemaSnapshotModel")
    except LookupError:
        return None


def _prune_snapshots(schema_name: str, model: Any) -> None:
    max_entries = get_setting("schema_registry.snapshot_max_entries", 50, schema_name)
    try:
        max_entries = int(max_entries)
    except (TypeError, ValueError):
        max_entries = 50
    if max_entries <= 0:
        return
    try:
        snapshots = model.objects.filter(schema_name=schema_name).order_by("-created_at")
        ids_to_keep = list(snapshots.values_list("id", flat=True)[:max_entries])
        model.objects.filter(schema_name=schema_name).exclude(id__in=ids_to_keep).delete()
    except (OperationalError, ProgrammingError):
        return
