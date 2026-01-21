"""
Security middleware for Rail Django GraphQL.

This module provides middleware for input validation, access control,
audit logging, and error handling for GraphQL operations.
"""

import logging
import time
from typing import Any, Callable, Optional

from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from .base import BaseMiddleware
from ..security import get_input_validator
from ..exceptions import ValidationError as GraphQLValidationError

logger = logging.getLogger(__name__)


class ValidationMiddleware(BaseMiddleware):
    """Middleware for input validation.

    This middleware validates all input arguments against configured
    validation rules and sanitization settings.
    """

    def __init__(self, schema_name: Optional[str] = None):
        """Initialize validation middleware.

        Args:
            schema_name: Optional schema name for schema-specific validation.
        """
        super().__init__(schema_name)
        self.input_validator = get_input_validator(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Validate GraphQL inputs.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Input arguments to validate.

        Returns:
            Resolver result.

        Raises:
            GraphQLValidationError: If input validation fails.
        """
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


class AccessGuardMiddleware(BaseMiddleware):
    """Middleware for schema-level authentication and introspection guards.

    This middleware enforces authentication requirements and introspection
    access controls at the schema level.
    """

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Enforce access control policies.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.

        Raises:
            PermissionError: If authentication or introspection is not permitted.
        """
        if not self._is_root_field(info):
            return next_resolver(root, info, **kwargs)

        from ..settings import SchemaSettings
        from ..security import is_introspection_allowed

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
        """Check if this is a root field resolution."""
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    @staticmethod
    def _is_restricted_introspection_field(info: Any) -> bool:
        """Check if this is a restricted introspection field."""
        field_name = getattr(info, "field_name", "") or ""
        return field_name in {"__schema", "__type"}


class GraphQLAuditMiddleware(BaseMiddleware):
    """Middleware for auditing GraphQL operations.

    This middleware records audit log entries for GraphQL operations,
    tracking who performed what action and when.
    """

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Record an audit entry for each root GraphQL operation.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.
        """
        if not getattr(settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True):
            return next_resolver(root, info, **kwargs)

        if not self._is_root_field(info):
            return next_resolver(root, info, **kwargs)

        try:
            from ...extensions.audit import AuditEventType, log_audit_event
        except Exception:
            return next_resolver(root, info, **kwargs)

        audit_wrapper = None
        try:
            from ...security.audit_logging import audit_graphql_operation
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
        """Check if this is a root field resolution."""
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    def _get_operation_name(self, info: Any) -> Optional[str]:
        """Get the operation name from the info object."""
        operation = getattr(info, "operation", None)
        name_node = getattr(operation, "name", None)
        if name_node and getattr(name_node, "value", None):
            return name_node.value
        return None

    def _resolve_event_type(
        self, operation_type: str, field_name: Optional[str], audit_enum: Any
    ) -> Any:
        """Resolve the audit event type for an operation."""
        op = (operation_type or "").lower()
        if op != "mutation":
            return audit_enum.DATA_ACCESS
        return self._resolve_mutation_event_type(field_name or "", audit_enum)

    def _resolve_mutation_event_type(self, field_name: str, audit_enum: Any) -> Any:
        """Resolve the audit event type for a mutation."""
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


class ErrorHandlingMiddleware(BaseMiddleware):
    """Middleware for error handling.

    This middleware catches and logs errors that occur during GraphQL
    resolution, providing consistent error handling and logging.
    """

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Handle and format GraphQL errors.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.

        Raises:
            The original exception after logging.
        """
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


class LoggingMiddleware(BaseMiddleware):
    """Middleware for logging GraphQL operations.

    This middleware logs the start and completion of GraphQL operations,
    including timing information and error details.
    """

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Log GraphQL operations.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.
        """
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
        """Check if this is an introspection field."""
        field_name = getattr(info, "field_name", "") or ""
        if field_name.startswith("__"):
            return True
        parent_type = getattr(info, "parent_type", None)
        parent_name = getattr(parent_type, "name", "") or ""
        return parent_name.startswith("__")
