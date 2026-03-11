"""
Auto Schema Generator - Builds schemas from explicit model lists.

This module provides the AutoSchemaGenerator class for building schemas
from explicit model lists with basic caching support.
"""

import itertools
import logging
import threading
from collections import OrderedDict
from typing import Any, Optional, Type

import graphene
from django.db import models

logger = logging.getLogger(__name__)


class AutoSchemaGenerator:
    """
    Builds schemas from explicit model lists with basic caching.

    This class provides an alternative to the SchemaBuilder for cases where
    you want to build schemas from specific model lists rather than
    auto-discovering models from Django apps.
    """

    _counter = itertools.count()

    def __init__(
        self,
        settings: Optional[Any] = None,
        schema_name: Optional[str] = None,
        registry=None,
        max_cached_builders: int = 32,
    ) -> None:
        """
        Initialize the AutoSchemaGenerator.

        Args:
            settings: Schema settings instance or None for defaults
            schema_name: Base name for generated schemas
            registry: Schema registry instance for model discovery
        """
        if schema_name is None:
            schema_name = f"auto_{next(self._counter)}"
        self._base_schema_name = schema_name
        self._settings = settings
        self._registry = registry
        self._registered_models: set[type[models.Model]] = set()
        self._query_extensions: list[type[graphene.ObjectType]] = []
        self._schema_cache: "OrderedDict[tuple[str, ...], graphene.Schema]" = (
            OrderedDict()
        )
        self._builders: "OrderedDict[tuple[str, ...], SchemaBuilder]" = OrderedDict()
        self._max_cached_builders = max(1, int(max_cached_builders))
        self._lock = threading.Lock()

    def _dispose_builder(self, builder: "SchemaBuilder") -> None:
        """Dispose of a cached builder that is no longer retained."""
        disconnect = getattr(builder, "disconnect_signals", None)
        if callable(disconnect):
            try:
                disconnect()
            except Exception as exc:
                logger.warning("Failed to disconnect auto schema builder: %s", exc)

    def _evict_oldest_builder_if_needed(self) -> None:
        """Bound builder growth across many distinct model-set combinations."""
        while len(self._builders) > self._max_cached_builders:
            cache_key, builder = self._builders.popitem(last=False)
            self._schema_cache.pop(cache_key, None)
            self._dispose_builder(builder)

    def register_model(self, model: type[models.Model]) -> None:
        """
        Register a single model for schema generation.

        Args:
            model: Django model class to register
        """
        self._registered_models.add(model)
        self._invalidate_cache()

    def register_models(self, models_list: list[type[models.Model]]) -> None:
        """
        Register multiple models for schema generation.

        Args:
            models_list: List of Django model classes to register
        """
        for model in models_list:
            self._registered_models.add(model)
        self._invalidate_cache()

    def add_query_extension(self, extension: type[graphene.ObjectType]) -> None:
        """
        Add a custom query extension to the schema.

        Args:
            extension: Query extension class to add
        """
        if extension not in self._query_extensions:
            self._query_extensions.append(extension)
            self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Invalidate all cached schemas."""
        self._schema_cache.clear()
        for builder in self._builders.values():
            builder.clear_schema()

    def _cache_key(
        self, models_list: Optional[list[type[models.Model]]]
    ) -> tuple[str, ...]:
        """
        Generate a cache key for a list of models.

        Args:
            models_list: List of models or None

        Returns:
            tuple[str, ...]: Cache key
        """
        if models_list is None:
            return ("__all__",)
        if not models_list:
            return ("__none__",)
        return tuple(sorted({model._meta.label_lower for model in models_list}))

    def _get_builder(self, cache_key: tuple[str, ...]) -> "SchemaBuilder":
        """
        Get or create a SchemaBuilder for the given cache key.

        Args:
            cache_key: Cache key for the builder

        Returns:
            SchemaBuilder: The schema builder instance
        """
        from . import SchemaBuilder

        builder = self._builders.get(cache_key)
        if builder is None:
            schema_name = f"{self._base_schema_name}_{len(self._builders)}"
            builder = SchemaBuilder(
                settings=self._settings,
                schema_name=schema_name,
                registry=self._registry,
            )
            self._builders[cache_key] = builder
            self._evict_oldest_builder_if_needed()
        else:
            self._builders.move_to_end(cache_key)
        return builder

    def get_schema(
        self, model_list: Optional[list[type[models.Model]]] = None
    ) -> graphene.Schema:
        """
        Get or build a schema for the given models.

        Args:
            model_list: Optional list of models. If None, uses registered models.

        Returns:
            graphene.Schema: The GraphQL schema
        """
        if model_list is None and self._registered_models:
            models_list = list(self._registered_models)
        else:
            models_list = list(model_list) if model_list is not None else None

        cache_key = self._cache_key(models_list)
        with self._lock:
            cached = self._schema_cache.get(cache_key)
            if cached is not None:
                self._schema_cache.move_to_end(cache_key)
                return cached

            builder = self._get_builder(cache_key)
            original_discover = getattr(builder, "_discover_models", None)
            original_load_query_extensions = getattr(builder, "_load_query_extensions", None)

            if models_list is not None:
                valid_models = [
                    model for model in models_list if builder._is_valid_model(model)
                ]

                def _discover_models_override() -> list[type[models.Model]]:
                    return valid_models

                builder._discover_models = _discover_models_override

            if self._query_extensions:
                def _load_query_extensions_override() -> (
                    list[type[graphene.ObjectType]]
                ):
                    loaded = list(original_load_query_extensions())
                    for extension in self._query_extensions:
                        if extension not in loaded:
                            loaded.append(extension)
                    return loaded

                builder._load_query_extensions = _load_query_extensions_override

            try:
                schema = builder.get_schema()
            finally:
                if models_list is not None and original_discover is not None:
                    builder._discover_models = original_discover
                if (
                    self._query_extensions
                    and original_load_query_extensions is not None
                ):
                    builder._load_query_extensions = original_load_query_extensions
            self._schema_cache[cache_key] = schema
            self._schema_cache.move_to_end(cache_key)
            while len(self._schema_cache) > self._max_cached_builders:
                self._schema_cache.popitem(last=False)
            return schema
