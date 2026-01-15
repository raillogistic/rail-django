"""
GraphQL middleware for Rail Django GraphQL.

This module implements middleware functionality defined in LIBRARY_DEFAULTS
including authentication, logging, performance monitoring, and error handling.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type, Union

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import models
from graphql import DocumentNode, GraphQLError

from .performance import get_complexity_analyzer
from .exceptions import ValidationError as GraphQLValidationError
from .security import get_auth_manager, get_input_validator
from .services import get_rate_limiter
from ..config_proxy import get_setting
from ..security.field_permissions import (
    FieldAccessLevel,
    FieldContext,
    FieldVisibility,
    field_permission_manager,
)
from ..plugins.base import plugin_manager

logger = logging.getLogger(__name__)


@dataclass
class MiddlewareSettings:
    """Settings for GraphQL middleware."""

    enable_authentication_middleware: bool = True
    enable_logging_middleware: bool = True
    enable_performance_middleware: bool = True
    enable_error_handling_middleware: bool = True
    enable_rate_limiting_middleware: bool = True
    enable_validation_middleware: bool = True
    enable_field_permission_middleware: bool = True
    enable_cors_middleware: bool = True
    log_queries: bool = True
    log_mutations: bool = True
    log_introspection: bool = False
    log_errors: bool = True
    log_performance: bool = True
    performance_threshold_ms: int = 1000
    enable_query_complexity_middleware: bool = True

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "MiddlewareSettings":
        """Create MiddlewareSettings from schema configuration."""
        from ..defaults import LIBRARY_DEFAULTS
        from django.conf import settings as django_settings

        defaults = LIBRARY_DEFAULTS.get("middleware_settings", {})

        # Allow Django settings to override defaults
        django_mw_settings = getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {}).get(
            "middleware_settings", {}
        )

        merged_settings = {**defaults, **django_mw_settings}

        # Filter to only include valid fields
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {k: v for k, v in merged_settings.items() if k in valid_fields}

        # No caching middleware in project

        return cls(**filtered_settings)


class BaseMiddleware:
    """Base class for GraphQL middleware."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = MiddlewareSettings.from_schema(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """
        Middleware resolve method.

        Args:
            next_resolver: Next resolver in the chain
            root: Root value
            info: GraphQL resolve info
            **kwargs: Additional arguments

        Returns:
            Resolver result
        """
        return next_resolver(root, info, **kwargs)


class AuthenticationMiddleware(BaseMiddleware):
    """Middleware for handling authentication."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.auth_manager = get_auth_manager(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Authenticate user and add to context."""
        if not self.settings.enable_authentication_middleware:
            return next_resolver(root, info, **kwargs)

        # Authenticate user if not already done
        if not hasattr(info.context, 'user'):
            user = self.auth_manager.authenticate_user(info.context)
            info.context.user = user

        return next_resolver(root, info, **kwargs)


class LoggingMiddleware(BaseMiddleware):
    """Middleware for logging GraphQL operations."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Log GraphQL operations."""
        if not self.settings.enable_logging_middleware:
            return next_resolver(root, info, **kwargs)

        operation_type = info.operation.operation.value if info.operation else "unknown"
        field_name = info.field_name

        # Log query/mutation start
        should_log = (
            (operation_type == "query" and self.settings.log_queries) or
            (operation_type == "mutation" and self.settings.log_mutations)
        )
        if should_log and not self.settings.log_introspection and self._is_introspection_field(info):
            should_log = False

        if should_log:
            user = getattr(info.context, 'user', AnonymousUser())
            user_id = user.id if hasattr(user, 'id') and user.id else "anonymous"

            logger.info(
                f"GraphQL {operation_type} started: {field_name} "
                f"(user: {user_id}, schema: {self.schema_name or 'default'})"
            )

        start_time = time.time()

        try:
            result = next_resolver(root, info, **kwargs)

            # Log successful completion
            if should_log:
                duration = (time.time() - start_time) * 1000
                logger.info(
                    f"GraphQL {operation_type} completed: {field_name} "
                    f"(duration: {duration:.2f}ms)"
                )

            return result

        except Exception as e:
            # Log errors
            if self.settings.log_errors:
                duration = (time.time() - start_time) * 1000
                logger.error(
                    f"GraphQL {operation_type} failed: {field_name} "
                    f"(duration: {duration:.2f}ms, error: {str(e)})"
                )

            raise

    @staticmethod
    def _is_introspection_field(info: Any) -> bool:
        field_name = getattr(info, "field_name", "") or ""
        if field_name.startswith("__"):
            return True
        parent_type = getattr(info, "parent_type", None)
        parent_name = getattr(parent_type, "name", "") or ""
        return parent_name.startswith("__")


class GraphQLAuditMiddleware(BaseMiddleware):
    """Middleware for auditing GraphQL operations."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Record an audit entry for each root GraphQL operation."""
        if not getattr(settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True):
            return next_resolver(root, info, **kwargs)

        if not self._is_root_field(info):
            return next_resolver(root, info, **kwargs)

        try:
            from ..extensions.audit import AuditEventType, log_audit_event
        except Exception:
            return next_resolver(root, info, **kwargs)

        audit_wrapper = None
        try:
            from ..security.audit_logging import audit_graphql_operation
            audit_wrapper = audit_graphql_operation
        except Exception:
            audit_wrapper = None

        operation_type = info.operation.operation.value if info.operation else "unknown"
        event_type = self._resolve_event_type(operation_type, info.field_name, AuditEventType)

        additional_data = {
            "graphql_operation": operation_type,
            "graphql_field": info.field_name,
            "schema_name": getattr(getattr(info, "context", None), "schema_name", None),
        }

        operation_name = self._get_operation_name(info)
        if operation_name:
            additional_data["graphql_operation_name"] = operation_name

        variables = getattr(info, "variable_values", None)
        if isinstance(variables, dict) and variables:
            additional_data["variable_keys"] = sorted(variables.keys())

        request = getattr(info, "context", None)
        success = True
        error_message = None

        resolver = next_resolver
        if audit_wrapper is not None:
            resolver = audit_wrapper(operation_type)(next_resolver)

        try:
            result = resolver(root, info, **kwargs)
            return result
        except Exception as exc:
            success = False
            error_message = str(exc)
            raise
        finally:
            log_audit_event(
                request,
                event_type,
                success=success,
                error_message=error_message,
                additional_data=additional_data,
            )

    def _is_root_field(self, info: Any) -> bool:
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    def _get_operation_name(self, info: Any) -> Optional[str]:
        operation = getattr(info, "operation", None)
        name_node = getattr(operation, "name", None)
        if name_node and getattr(name_node, "value", None):
            return name_node.value
        return None

    def _resolve_event_type(
        self, operation_type: str, field_name: Optional[str], audit_enum: Any
    ) -> Any:
        op = (operation_type or "").lower()
        if op != "mutation":
            return audit_enum.DATA_ACCESS
        return self._resolve_mutation_event_type(field_name or "", audit_enum)

    def _resolve_mutation_event_type(self, field_name: str, audit_enum: Any) -> Any:
        name = field_name.lower()

        if name.startswith(("create", "add", "register", "signup", "import")):
            return audit_enum.CREATE
        if name.startswith(("delete", "remove", "archive", "purge", "clear")):
            return audit_enum.DELETE
        if name.startswith(("update", "set", "edit", "patch", "upsert", "enable", "disable")):
            return audit_enum.UPDATE

        if "delete" in name or "remove" in name:
            return audit_enum.DELETE
        if "create" in name or "add" in name:
            return audit_enum.CREATE
        if "update" in name or "set" in name or "edit" in name:
            return audit_enum.UPDATE

        return audit_enum.UPDATE


class PerformanceMiddleware(BaseMiddleware):
    """Middleware for performance monitoring."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Monitor performance of GraphQL operations."""
        if not self.settings.enable_performance_middleware:
            return next_resolver(root, info, **kwargs)

        start_time = time.time()

        try:
            result = next_resolver(root, info, **kwargs)

            # Check performance threshold
            duration_ms = (time.time() - start_time) * 1000

            if duration_ms > self.settings.performance_threshold_ms and self.settings.log_performance:
                operation_type = info.operation.operation.value if info.operation else "unknown"
                field_name = info.field_name

                logger.warning(
                    f"Slow GraphQL {operation_type}: {field_name} "
                    f"(duration: {duration_ms:.2f}ms, threshold: {self.settings.performance_threshold_ms}ms)"
                )

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"GraphQL operation failed after {duration_ms:.2f}ms: {str(e)}")
            raise


class RateLimitingMiddleware(BaseMiddleware):
    """Middleware for rate limiting."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.rate_limiter = get_rate_limiter(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Apply rate limiting to GraphQL operations."""
        if not self.settings.enable_rate_limiting_middleware:
            return next_resolver(root, info, **kwargs)

        if not self._is_root_field(info):
            return next_resolver(root, info, **kwargs)

        result = self.rate_limiter.check("graphql", request=info.context)
        if not result.allowed:
            raise PermissionError("Rate limit exceeded")

        if self._is_login_field(info):
            login_result = self.rate_limiter.check("graphql_login", request=info.context)
            if not login_result.allowed:
                raise PermissionError("Rate limit exceeded (login)")

        return next_resolver(root, info, **kwargs)

    @staticmethod
    def _is_root_field(info: Any) -> bool:
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    @staticmethod
    def _is_login_field(info: Any) -> bool:
        field_name = getattr(info, "field_name", "") or ""
        return field_name.lower() == "login"


class AccessGuardMiddleware(BaseMiddleware):
    """Middleware for schema-level authentication and introspection guards."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        if not self._is_root_field(info):
            return next_resolver(root, info, **kwargs)

        from .settings import SchemaSettings
        from .security import is_introspection_allowed

        schema_name = getattr(info.context, "schema_name", None)
        schema_settings = SchemaSettings.from_schema(schema_name)
        user = getattr(info.context, "user", None)

        if schema_settings.authentication_required:
            if not user or not getattr(user, "is_authenticated", False):
                raise PermissionError("Authentication required")

        if self._is_restricted_introspection_field(info):
            if not is_introspection_allowed(
                user,
                schema_name,
                enable_introspection=schema_settings.enable_introspection,
            ):
                raise PermissionError("Introspection not permitted")

        return next_resolver(root, info, **kwargs)

    @staticmethod
    def _is_root_field(info: Any) -> bool:
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    @staticmethod
    def _is_restricted_introspection_field(info: Any) -> bool:
        field_name = getattr(info, "field_name", "") or ""
        return field_name in {"__schema", "__type"}


## CachingMiddleware removed: caching is not supported in this project.


class ValidationMiddleware(BaseMiddleware):
    """Middleware for input validation."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.input_validator = get_input_validator(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Validate GraphQL inputs."""
        if not self.settings.enable_validation_middleware:
            return next_resolver(root, info, **kwargs)

        # Validate input arguments
        if kwargs:
            report = self.input_validator.validate_payload(kwargs)
            if report.has_failures():
                raise GraphQLValidationError(
                    "Input validation failed",
                    validation_errors=report.as_error_dict(),
                )
            if isinstance(report.sanitized_data, dict):
                kwargs = report.sanitized_data

        return next_resolver(root, info, **kwargs)


class FieldPermissionMiddleware(BaseMiddleware):
    """Middleware for field output masking and input enforcement."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.input_mode = str(
            get_setting(
                "security_settings.field_permission_input_mode",
                "reject",
                schema_name,
            )
        ).lower()
        self.enable_field_permissions = bool(
            get_setting("security_settings.enable_field_permissions", True, schema_name)
        )

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        if (
            not self.settings.enable_field_permission_middleware
            or not self.enable_field_permissions
        ):
            return next_resolver(root, info, **kwargs)

        if self._is_introspection_field(info):
            return next_resolver(root, info, **kwargs)

        user = getattr(info.context, "user", None)

        if self._is_root_field(info) and self._is_mutation(info):
            kwargs = self._enforce_input_permissions(user, info, kwargs)

        result = next_resolver(root, info, **kwargs)
        return self._apply_output_permissions(user, info, root, result)

    @staticmethod
    def _is_root_field(info: Any) -> bool:
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    @staticmethod
    def _is_introspection_field(info: Any) -> bool:
        field_name = getattr(info, "field_name", "") or ""
        if field_name.startswith("__"):
            return True
        parent_type = getattr(info, "parent_type", None)
        parent_name = getattr(parent_type, "name", "") or ""
        return parent_name.startswith("__")

    @staticmethod
    def _is_mutation(info: Any) -> bool:
        operation = getattr(info, "operation", None)
        return bool(
            operation and getattr(operation, "operation", None) and
            operation.operation.value == "mutation"
        )

    @staticmethod
    def _unwrap_graphql_type(graphql_type: Any) -> Any:
        while hasattr(graphql_type, "of_type"):
            graphql_type = graphql_type.of_type
        return graphql_type

    def _resolve_parent_model_class(
        self, info: Any, root: Any, result: Any
    ) -> Optional[type[models.Model]]:
        if isinstance(root, models.Model):
            return root.__class__
        parent_type = self._unwrap_graphql_type(getattr(info, "parent_type", None))
        graphene_type = getattr(parent_type, "graphene_type", None)
        meta = getattr(graphene_type, "_meta", None)
        model_class = getattr(meta, "model", None)
        if model_class is not None:
            return model_class
        if isinstance(result, models.Model):
            return result.__class__
        return None

    def _resolve_mutation_model_class(self, info: Any) -> Optional[type[models.Model]]:
        graphql_type = self._unwrap_graphql_type(getattr(info, "return_type", None))
        graphene_type = getattr(graphql_type, "graphene_type", None)
        if graphene_type is None:
            return None
        model_class = getattr(graphene_type, "model_class", None)
        if model_class is not None:
            return model_class
        meta = getattr(graphene_type, "_meta", None)
        return getattr(meta, "model", None)

    def _resolve_operation_type(self, info: Any) -> str:
        operation = getattr(info, "operation", None)
        op_value = (
            operation.operation.value
            if operation and getattr(operation, "operation", None)
            else "query"
        )
        if op_value == "mutation":
            return self._resolve_mutation_operation(info.field_name or "")
        return "read"

    @staticmethod
    def _resolve_mutation_operation(field_name: str) -> str:
        name = (field_name or "").lower()
        if name.startswith("bulk"):
            name = name[4:]
        if name.startswith(("create", "add", "register", "signup", "import")):
            return "create"
        if name.startswith(("delete", "remove", "archive", "purge", "clear")):
            return "delete"
        if name.startswith(("update", "set", "edit", "patch", "upsert", "enable", "disable")):
            return "update"
        if "delete" in name or "remove" in name:
            return "delete"
        if "create" in name or "add" in name:
            return "create"
        if "update" in name or "edit" in name or "patch" in name:
            return "update"
        return "write"

    @staticmethod
    def _normalize_payload(payload: Any) -> Optional[dict[str, Any]]:
        if payload is None:
            return None
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "items"):
            try:
                return dict(payload.items())
            except Exception:
                return dict(payload)
        if hasattr(payload, "__dict__"):
            return {
                key: value
                for key, value in vars(payload).items()
                if not key.startswith("_")
            }
        return None

    @staticmethod
    def _resolve_instance(
        model_class: type[models.Model], object_id: Any
    ) -> Optional[models.Model]:
        if object_id is None:
            return None
        try:
            return model_class.objects.get(pk=object_id)
        except Exception:
            try:
                from graphql_relay import from_global_id

                decoded_type, decoded_id = from_global_id(str(object_id))
                return model_class.objects.get(pk=decoded_id)
            except Exception:
                return None

    def _enforce_input_permissions(
        self, user: Any, info: Any, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        model_class = self._resolve_mutation_model_class(info)
        if model_class is None:
            return kwargs

        operation = self._resolve_operation_type(info)
        if operation == "delete":
            return kwargs
        if operation == "write":
            operation = "update"

        request_context = {"request": getattr(info, "context", None)}
        disallowed_fields: list[str] = []
        updated_kwargs = dict(kwargs)

        def _check_payload(payload: Any, object_id: Any = None) -> Any:
            payload_dict = self._normalize_payload(payload)
            if payload_dict is None:
                return payload
            target_payload = (
                payload_dict.get("data")
                if isinstance(payload_dict.get("data"), dict)
                else payload_dict
            )
            instance = None
            if object_id is not None:
                instance = self._resolve_instance(model_class, object_id)
            blocked = []
            for field_name in list(target_payload.keys()):
                if field_name in {"id", "pk", "object_id"}:
                    continue
                base_field = field_name
                if base_field.startswith("nested_"):
                    base_field = base_field[len("nested_") :]
                field_context = FieldContext(
                    user=user,
                    instance=instance,
                    field_name=base_field,
                    operation_type=operation,
                    model_class=model_class,
                    request_context=request_context,
                )
                access_level = field_permission_manager.get_field_access_level(
                    field_context
                )
                if access_level not in (
                    FieldAccessLevel.WRITE,
                    FieldAccessLevel.ADMIN,
                ):
                    blocked.append(field_name)
            if blocked and self.input_mode == "strip":
                for field_name in blocked:
                    target_payload.pop(field_name, None)
            disallowed_fields.extend(blocked)
            return payload_dict

        if "input" in updated_kwargs:
            object_id = updated_kwargs.get("id") or updated_kwargs.get("object_id")
            updated_kwargs["input"] = _check_payload(
                updated_kwargs["input"], object_id=object_id
            )

        if "inputs" in updated_kwargs and isinstance(updated_kwargs["inputs"], list):
            sanitized_inputs = []
            for payload in updated_kwargs["inputs"]:
                payload_dict = self._normalize_payload(payload) or {}
                object_id = (
                    payload_dict.get("id")
                    or payload_dict.get("pk")
                    or payload_dict.get("object_id")
                )
                sanitized_inputs.append(_check_payload(payload, object_id=object_id))
            updated_kwargs["inputs"] = sanitized_inputs

        if disallowed_fields and self.input_mode != "strip":
            raise GraphQLError(
                f"Input fields not permitted: {', '.join(sorted(set(disallowed_fields)))}"
            )

        return updated_kwargs

    def _apply_output_permissions(
        self, user: Any, info: Any, root: Any, result: Any
    ) -> Any:
        field_name = getattr(info, "field_name", None)
        if not field_name:
            return result
        model_class = self._resolve_parent_model_class(info, root, result)
        if model_class is None:
            return result

        instance = root if isinstance(root, models.Model) else None
        operation = self._resolve_operation_type(info)
        field_context = FieldContext(
            user=user,
            instance=instance,
            field_name=field_name,
            operation_type=operation,
            model_class=model_class,
            request_context={"request": getattr(info, "context", None)},
        )
        visibility, mask_value = field_permission_manager.get_field_visibility(
            field_context
        )

        if visibility == FieldVisibility.HIDDEN:
            return None
        if visibility == FieldVisibility.MASKED:
            return mask_value
        if visibility == FieldVisibility.REDACTED:
            return self._redact_value(result)

        return result

    @staticmethod
    def _redact_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            if len(value) > 4:
                return value[:2] + "*" * (len(value) - 4) + value[-2:]
            return "****"
        return "****"


class ErrorHandlingMiddleware(BaseMiddleware):
    """Middleware for error handling."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Handle and format GraphQL errors."""
        if not self.settings.enable_error_handling_middleware:
            return next_resolver(root, info, **kwargs)

        try:
            return next_resolver(root, info, **kwargs)

        except PermissionError as e:
            # Handle permission errors
            logger.warning(f"Permission denied: {str(e)}")
            raise

        except ValueError as e:
            # Handle validation errors
            logger.warning(f"Validation error: {str(e)}")
            raise

        except Exception as e:
            # Handle unexpected errors
            operation_type = info.operation.operation.value if info.operation else "unknown"
            field_name = info.field_name

            logger.error(
                f"Unexpected error in GraphQL {operation_type} {field_name}: {str(e)}",
                exc_info=True
            )

            # Re-raise the original exception
            raise


class QueryComplexityMiddleware(BaseMiddleware):
    """Middleware for query complexity analysis."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.complexity_analyzer = get_complexity_analyzer(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Analyze and limit query complexity."""
        if not self.settings.enable_query_complexity_middleware:
            return next_resolver(root, info, **kwargs)

        # Only analyze queries
        operation_type = info.operation.operation.value if info.operation else "unknown"
        if operation_type != "query":
            return next_resolver(root, info, **kwargs)

        # Analyze query complexity
        query_string = str(info.operation)
        fragments = list(getattr(info, "fragments", {}).values())
        document = (
            DocumentNode(definitions=[info.operation] + fragments)
            if info.operation is not None
            else None
        )
        try:
            depth, complexity = self.complexity_analyzer.analyze_query(query_string)
            metrics = getattr(info.context, "_graphql_metrics", None)
            if metrics is not None:
                metrics.query_depth = depth
                metrics.query_complexity = complexity
        except Exception:
            pass
        validation_errors = self.complexity_analyzer.validate_query_limits(
            query_string,
            schema=getattr(info, "schema", None),
            document=document,
        )

        if validation_errors:
            raise ValueError(f"Query complexity validation failed: {'; '.join(validation_errors)}")

        return next_resolver(root, info, **kwargs)


class PluginMiddleware(BaseMiddleware):
    """Middleware for plugin execution hooks."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.enabled = bool(
            get_setting("plugin_settings.enable_execution_hooks", True, schema_name)
        )

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        if not self.enabled:
            return next_resolver(root, info, **kwargs)

        schema_name = getattr(info.context, "schema_name", None) or self.schema_name
        operation_type = info.operation.operation.value if info.operation else "unknown"
        operation_name = self._get_operation_name(info)
        context = self._get_plugin_context(info)
        is_root = self._is_root_field(info)

        if is_root:
            decision = plugin_manager.run_before_operation(
                schema_name, operation_type, operation_name, info, context
            )
            if decision and decision.handled:
                return decision.result

        decision = plugin_manager.run_before_resolve(
            schema_name, info, root, kwargs, context
        )
        if decision and decision.handled:
            return decision.result

        try:
            result = next_resolver(root, info, **kwargs)
        except Exception as exc:
            plugin_manager.run_after_resolve(
                schema_name, info, root, kwargs, None, exc, context
            )
            if is_root:
                plugin_manager.run_after_operation(
                    schema_name, operation_type, operation_name, info, None, exc, context
                )
            raise

        after_resolve = plugin_manager.run_after_resolve(
            schema_name, info, root, kwargs, result, None, context
        )
        if after_resolve and after_resolve.handled:
            result = after_resolve.result

        if is_root:
            after_operation = plugin_manager.run_after_operation(
                schema_name, operation_type, operation_name, info, result, None, context
            )
            if after_operation and after_operation.handled:
                result = after_operation.result

        return result

    @staticmethod
    def _get_plugin_context(info: Any) -> dict[str, Any]:
        context = getattr(info.context, "_rail_plugin_context", None)
        if context is None:
            context = {}
            setattr(info.context, "_rail_plugin_context", context)
        return context

    @staticmethod
    def _is_root_field(info: Any) -> bool:
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    @staticmethod
    def _get_operation_name(info: Any) -> Optional[str]:
        operation = getattr(info, "operation", None)
        name_node = getattr(operation, "name", None)
        if name_node and getattr(name_node, "value", None):
            return name_node.value
        return None


class CORSMiddleware(BaseMiddleware):
    """Middleware for CORS handling."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Handle CORS for GraphQL requests."""
        if not self.settings.enable_cors_middleware:
            return next_resolver(root, info, **kwargs)

        # CORS headers are typically handled at the HTTP level
        # This middleware can add additional CORS-related logic if needed

        return next_resolver(root, info, **kwargs)


# Default middleware stack
DEFAULT_MIDDLEWARE = [
    AuthenticationMiddleware,
    GraphQLAuditMiddleware,
    RateLimitingMiddleware,
    AccessGuardMiddleware,
    ValidationMiddleware,
    FieldPermissionMiddleware,
    QueryComplexityMiddleware,
    PluginMiddleware,
    PerformanceMiddleware,
    LoggingMiddleware,
    ErrorHandlingMiddleware,
    CORSMiddleware,
]


def get_middleware_stack(schema_name: Optional[str] = None) -> list[BaseMiddleware]:
    """
    Get the middleware stack for a schema.

    Args:
        schema_name: Schema name (optional)

    Returns:
        List of middleware instances
    """
    middleware_stack = []

    for middleware_class in DEFAULT_MIDDLEWARE:
        middleware_instance = middleware_class(schema_name)
        middleware_stack.append(middleware_instance)

    return middleware_stack


def create_middleware_resolver(middleware_stack: list[BaseMiddleware]) -> Callable:
    """
    Create a resolver that applies middleware stack.

    Args:
        middleware_stack: List of middleware instances

    Returns:
        Middleware resolver function
    """
    def middleware_resolver(next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Apply middleware stack to resolver."""

        def apply_middleware(index: int) -> Any:
            if index >= len(middleware_stack):
                return next_resolver(root, info, **kwargs)

            middleware = middleware_stack[index]

            def next_middleware_resolver(r, i, **kw):
                return apply_middleware(index + 1)

            return middleware.resolve(next_middleware_resolver, root, info, **kwargs)

        return apply_middleware(0)

    return middleware_resolver
