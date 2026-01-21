"""
Registration and update logic for SchemaManager.
"""

import logging
from datetime import datetime
from typing import Any, Optional, Union

from graphql import GraphQLSchema, build_ast_schema

from ...validation import SchemaInfo
from .lifecycle import SchemaOperation, SchemaStatus, SchemaMetadata

logger = logging.getLogger(__name__)


class SchemaRegistrationMixin:
    """Mixin for schema registration and updates."""

    def register_schema(self,
                        name: str,
                        schema: Union[GraphQLSchema, str],
                        version: str = "1.0.0",
                        description: str = "",
                        user_id: str = None,
                        tags: dict[str, str] = None,
                        dependencies: list[str] = None,
                        force: bool = False) -> bool:
        """Register a new GraphQL schema."""
        event = self._create_event(
            schema_name=name,
            operation=SchemaOperation.REGISTER,
            user_id=user_id
        )

        try:
            start_time = datetime.now()
            self._execute_hooks(SchemaOperation.REGISTER, 'pre', {
                'name': name, 'schema': schema, 'version': version, 'user_id': user_id
            })

            if isinstance(schema, str):
                try:
                    schema = build_ast_schema(schema)
                except Exception as e:
                    raise ValueError(f"Invalid GraphQL SDL: {e}")

            if not force:
                schema_info = SchemaInfo(name=name, schema=schema, version=version, description=description)
                validation_result = self.validator.validate_schema(schema_info)
                if not validation_result.is_valid:
                    raise ValueError(f"Schema validation failed: {validation_result.errors}")

            if name in self._schemas and not force:
                existing_metadata = self._metadata.get(name)
                if existing_metadata and existing_metadata.version == version:
                    raise ValueError(f"Schema {name} version {version} already exists")

            with self._lock:
                self._schemas[name] = schema
                metadata = SchemaMetadata(
                    name=name, version=version, description=description, status=SchemaStatus.ACTIVE,
                    created_at=datetime.now(), updated_at=datetime.now(), created_by=user_id, updated_by=user_id,
                    tags=tags or {}, dependencies=dependencies or []
                )
                self._metadata[name] = metadata
                from .health import SchemaHealth
                self._health_status[name] = SchemaHealth(schema_name=name, status='healthy', last_check=datetime.now())
                if self.enable_caching: self._clear_schema_cache(name)

            event.success = True
            event.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            event.details = {'version': version, 'description': description, 'tags': tags or {}, 'dependencies': dependencies or []}

            self._execute_hooks(SchemaOperation.REGISTER, 'post', {
                'name': name, 'schema': schema, 'metadata': metadata, 'event': event
            })

            if self.debug_hooks:
                self.debug_hooks.log_schema_registration(schema_name=name, version=version, success=True)

            logger.info(f"Schema registered successfully: {name} v{version}")
            return True

        except Exception as e:
            event.success = False
            event.error_message = str(e)
            if self.debug_hooks:
                self.debug_hooks.log_schema_registration(schema_name=name, version=version, success=False, error=str(e))
            logger.error(f"Schema registration failed: {name} - {e}")
            raise
        finally:
            self._lifecycle_events.append(event)

    def update_schema(self,
                      name: str,
                      schema: Union[GraphQLSchema, str] = None,
                      version: str = None,
                      description: str = None,
                      user_id: str = None,
                      tags: dict[str, str] = None,
                      force: bool = False) -> bool:
        """Update an existing schema."""
        if name not in self._schemas: raise ValueError(f"Schema {name} not found")
        event = self._create_event(schema_name=name, operation=SchemaOperation.UPDATE, user_id=user_id)

        try:
            start_time = datetime.now()
            self._execute_hooks(SchemaOperation.UPDATE, 'pre', {
                'name': name, 'schema': schema, 'version': version, 'user_id': user_id
            })

            with self._lock:
                current_metadata = self._metadata[name]
                old_schema = self._schemas[name]
                updates = {}

                if schema is not None:
                    if isinstance(schema, str): schema = build_ast_schema(schema)
                    if not force:
                        schema_info = SchemaInfo(name=name, schema=schema, version=version or current_metadata.version, description=description or current_metadata.description)
                        validation_result = self.validator.validate_schema(schema_info)
                        if not validation_result.is_valid:
                            raise ValueError(f"Schema validation failed: {validation_result.errors}")
                    updates['schema'] = schema

                if version is not None: updates['version'] = version
                if description is not None: updates['description'] = description
                if tags is not None: updates['tags'] = {**current_metadata.tags, **tags}

                if 'schema' in updates: self._schemas[name] = updates['schema']
                for key, value in updates.items():
                    if key != 'schema': setattr(current_metadata, key, value)

                current_metadata.updated_at = datetime.now()
                current_metadata.updated_by = user_id
                if self.enable_caching: self._clear_schema_cache(name)

            event.success = True
            event.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            event.details = updates

            self._execute_hooks(SchemaOperation.UPDATE, 'post', {
                'name': name, 'old_schema': old_schema, 'new_schema': self._schemas[name], 'metadata': current_metadata, 'event': event
            })

            logger.info(f"Schema updated successfully: {name}")
            return True

        except Exception as e:
            event.success = False
            event.error_message = str(e)
            logger.error(f"Schema update failed: {name} - {e}")
            raise
        finally:
            self._lifecycle_events.append(event)
