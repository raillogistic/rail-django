"""
SchemaManager implementation.
"""

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Union, Tuple

from graphql import GraphQLSchema

from ...debugging import DebugHooks, PerformanceMonitor
from ...introspection import SchemaIntrospector
from ...validation import SchemaValidator

from .lifecycle import (
    SchemaLifecycleEvent,
    SchemaMetadata,
    SchemaOperation,
    SchemaStatus,
)
from .health import SchemaHealth
from .registration import SchemaRegistrationMixin
from .health_monitor import SchemaHealthMixin
from .export import SchemaExportMixin

logger = logging.getLogger(__name__)


class SchemaManager(SchemaRegistrationMixin, SchemaHealthMixin, SchemaExportMixin):
    """
    Comprehensive schema lifecycle management system.
    """

    def __init__(self,
                 validator: SchemaValidator = None,
                 introspector: SchemaIntrospector = None,
                 debug_hooks: DebugHooks = None,
                 performance_monitor: PerformanceMonitor = None,
                 enable_caching: bool = True,
                 cache_timeout: int = 3600,
                 enable_health_monitoring: bool = True,
                 health_check_interval: int = 300):

        self.validator = validator or SchemaValidator()
        self.introspector = introspector or SchemaIntrospector()
        self.debug_hooks = debug_hooks
        self.performance_monitor = performance_monitor
        self.enable_caching = enable_caching
        self.cache_timeout = cache_timeout
        self.enable_health_monitoring = enable_health_monitoring
        self.health_check_interval = health_check_interval

        self._schemas: dict[str, GraphQLSchema] = {}
        self._schema_cache: dict[str, tuple[GraphQLSchema, float]] = {}
        self._metadata: dict[str, SchemaMetadata] = {}
        self._lifecycle_events: list[SchemaLifecycleEvent] = []
        self._health_status: dict[str, SchemaHealth] = {}

        self._pre_operation_hooks: dict[SchemaOperation, list[Callable]] = defaultdict(list)
        self._post_operation_hooks: dict[SchemaOperation, list[Callable]] = defaultdict(list)

        self._lock = threading.RLock()
        self._health_monitor_thread = None
        self._stop_health_monitor = threading.Event()

        if self.enable_health_monitoring:
            self._start_health_monitoring()

        self.logger = logging.getLogger(__name__)

    def deactivate_schema(self, name: str, user_id: str = None) -> bool:
        """Deactivate a schema."""
        return self._change_schema_status(name, SchemaStatus.INACTIVE, user_id)

    def activate_schema(self, name: str, user_id: str = None) -> bool:
        """Activate a schema."""
        return self._change_schema_status(name, SchemaStatus.ACTIVE, user_id)

    def deprecate_schema(self, name: str, deprecation_date: datetime = None,
                         migration_path: str = None, user_id: str = None) -> bool:
        """Deprecate a schema with optional migration path."""
        if name not in self._schemas: raise ValueError(f"Schema {name} not found")
        with self._lock:
            metadata = self._metadata[name]
            metadata.status = SchemaStatus.DEPRECATED
            metadata.deprecation_date = deprecation_date or datetime.now()
            metadata.migration_path = migration_path
            metadata.updated_at = datetime.now()
            metadata.updated_by = user_id
        logger.info(f"Schema deprecated: {name}")
        return True

    def delete_schema(self, name: str, user_id: str = None, force: bool = False) -> bool:
        """Delete a schema."""
        if name not in self._schemas: raise ValueError(f"Schema {name} not found")
        event = self._create_event(schema_name=name, operation=SchemaOperation.DELETE, user_id=user_id)
        try:
            with self._lock:
                metadata = self._metadata[name]
                if not force and metadata.status == SchemaStatus.ACTIVE:
                    raise ValueError(f"Cannot delete active schema {name}. Deactivate first or use force=True")
                self._execute_hooks(SchemaOperation.DELETE, 'pre', {'name': name, 'metadata': metadata, 'user_id': user_id})
                del self._schemas[name]
                del self._metadata[name]
                if name in self._health_status: del self._health_status[name]
                if self.enable_caching: self._clear_schema_cache(name)
            event.success = True
            self._execute_hooks(SchemaOperation.DELETE, 'post', {'name': name, 'event': event})
            logger.info(f"Schema deleted: {name}")
            return True
        except Exception as e:
            event.success = False
            event.error_message = str(e)
            logger.error(f"Schema deletion failed: {name} - {e}")
            raise
        finally:
            self._lifecycle_events.append(event)

    def get_schema(self, name: str, use_cache: bool = True) -> Optional[GraphQLSchema]:
        """Get schema by name."""
        if use_cache and self.enable_caching:
            cached = self._schema_cache.get(name)
            if cached:
                schema, expires_at = cached
                if expires_at > time.time(): return schema
                self._schema_cache.pop(name, None)
        schema = self._schemas.get(name)
        if schema and use_cache and self.enable_caching:
            self._schema_cache[name] = (schema, time.time() + float(self.cache_timeout))
        return schema

    def get_schema_metadata(self, name: str) -> Optional[SchemaMetadata]:
        """Get schema metadata by name."""
        return self._metadata.get(name)

    def list_schemas(self, status: SchemaStatus = None, tags: dict[str, str] = None, include_deprecated: bool = True) -> list[SchemaMetadata]:
        """List schemas with optional filtering."""
        schemas = []
        with self._lock:
            for metadata in self._metadata.values():
                if status and metadata.status != status: continue
                if not include_deprecated and metadata.status == SchemaStatus.DEPRECATED: continue
                if tags and not all(metadata.tags.get(key) == value for key, value in tags.items()): continue
                schemas.append(metadata)
        schemas.sort(key=lambda s: s.name)
        return schemas

    def get_schema_health(self, name: str) -> Optional[SchemaHealth]:
        """Get schema health status."""
        return self._health_status.get(name)

    def get_lifecycle_events(self, schema_name: str = None, operation: SchemaOperation = None,
                             hours_back: int = 24, limit: int = 100) -> list[SchemaLifecycleEvent]:
        """Get lifecycle events with optional filtering."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        events = []
        for event in reversed(self._lifecycle_events):
            if event.timestamp < cutoff_time: continue
            if schema_name and event.schema_name != schema_name: continue
            if operation and event.operation != operation: continue
            events.append(event)
            if len(events) >= limit: break
        return events

    def add_lifecycle_hook(self, operation: SchemaOperation, hook: Callable, when: str = 'post'):
        """Add lifecycle hook."""
        if when == 'pre': self._pre_operation_hooks[operation].append(hook)
        elif when == 'post': self._post_operation_hooks[operation].append(hook)
        else: raise ValueError("when must be 'pre' or 'post'")

    def cleanup_old_events(self, days_to_keep: int = 30):
        """Clean up old lifecycle events."""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        with self._lock:
            self._lifecycle_events = [e for e in self._lifecycle_events if e.timestamp >= cutoff_date]
        logger.info(f"Cleaned up lifecycle events older than {days_to_keep} days")

    def _change_schema_status(self, name: str, status: SchemaStatus, user_id: str = None) -> bool:
        if name not in self._schemas: raise ValueError(f"Schema {name} not found")
        operation = SchemaOperation.ACTIVATE if status == SchemaStatus.ACTIVE else SchemaOperation.DEACTIVATE
        event = self._create_event(schema_name=name, operation=operation, user_id=user_id)
        try:
            with self._lock:
                metadata = self._metadata[name]
                old_status = metadata.status
                metadata.status = status
                metadata.updated_at = datetime.now()
                metadata.updated_by = user_id
                if self.enable_caching: self._clear_schema_cache(name)
            event.success = True
            event.details = {'old_status': old_status.value, 'new_status': status.value}
            logger.info(f"Schema status changed: {name} {old_status.value} -> {status.value}")
            return True
        except Exception as e:
            event.success = False
            event.error_message = str(e)
            raise
        finally:
            self._lifecycle_events.append(event)

    def _create_event(self, schema_name: str, operation: SchemaOperation, user_id: str = None) -> SchemaLifecycleEvent:
        return SchemaLifecycleEvent(event_id=f"{operation.value}_{schema_name}_{datetime.now().isoformat()}",
                                    schema_name=schema_name, operation=operation, timestamp=datetime.now(), user_id=user_id)

    def _execute_hooks(self, operation: SchemaOperation, when: str, context: dict[str, Any]):
        hooks = self._pre_operation_hooks[operation] if when == 'pre' else self._post_operation_hooks[operation]
        for hook in hooks:
            try: hook(context)
            except Exception as e: logger.error(f"Error in {when}-{operation.value} hook: {e}")

    def _clear_schema_cache(self, name: str):
        self._schema_cache.pop(name, None)

    def stop(self):
        if self._health_monitor_thread:
            self._stop_health_monitor.set()
            self._health_monitor_thread.join(timeout=5)
        logger.info("Schema manager stopped")

    def __del__(self):
        try: self.stop()
        except: pass