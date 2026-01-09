"""
Error handling utilities for Rail Django GraphQL.

This module implements error handling functionality defined in LIBRARY_DEFAULTS
including custom error types, error formatting, and error reporting.
"""

import logging
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from django.conf import settings as django_settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from graphql.error import GraphQLError
from graphql.execution import ExecutionResult

from ..conf import get_setting

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorHandlingSettings:
    """Settings for error handling."""

    enable_detailed_errors: bool = False  # Only in development
    enable_error_logging: bool = True
    enable_error_reporting: bool = True
    enable_sentry_integration: bool = False
    mask_internal_errors: bool = True
    include_stack_trace: bool = False  # Only in development
    error_code_prefix: str = "RAIL_GQL"
    max_error_message_length: int = 500
    enable_error_categorization: bool = True
    enable_error_metrics: bool = True
    log_level: str = "ERROR"

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "ErrorHandlingSettings":
        """Create ErrorHandlingSettings from schema configuration."""
        from ..defaults import LIBRARY_DEFAULTS

        defaults = LIBRARY_DEFAULTS.get("error_handling", {})

        # Override with Django settings if available
        django_error_settings = getattr(
            django_settings, 'RAIL_DJANGO_GRAPHQL', {}).get('error_handling', {})

        # Merge settings
        merged_settings = {**defaults, **django_error_settings}

        # Adjust settings based on DEBUG mode
        if django_settings.DEBUG:
            merged_settings.setdefault('enable_detailed_errors', True)
            merged_settings.setdefault('include_stack_trace', True)
            merged_settings.setdefault('mask_internal_errors', False)

        # Filter to only include valid fields
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {k: v for k, v in merged_settings.items() if k in valid_fields}

        return cls(**filtered_settings)


class RailGraphQLError(GraphQLError):
    """Base class for Rail Django GraphQL errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        extensions: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        self.code = code
        self.severity = severity

        # Prepare extensions
        error_extensions = extensions or {}
        if code:
            error_extensions['code'] = code
        error_extensions['severity'] = severity.value

        super().__init__(message, extensions=error_extensions, **kwargs)


class ValidationError(RailGraphQLError):
    """Error for validation failures."""

    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        code = kwargs.pop('code', 'VALIDATION_ERROR')
        severity = kwargs.pop('severity', ErrorSeverity.LOW)

        extensions = kwargs.pop('extensions', {})
        if field:
            extensions['field'] = field

        super().__init__(message, code=code, severity=severity, extensions=extensions, **kwargs)


class AuthenticationError(RailGraphQLError):
    """Error for authentication failures."""

    def __init__(self, message: str = "Authentication required", **kwargs):
        code = kwargs.pop('code', 'AUTHENTICATION_ERROR')
        severity = kwargs.pop('severity', ErrorSeverity.MEDIUM)

        super().__init__(message, code=code, severity=severity, **kwargs)


class AuthorizationError(RailGraphQLError):
    """Error for authorization failures."""

    def __init__(self, message: str = "Permission denied", **kwargs):
        code = kwargs.pop('code', 'AUTHORIZATION_ERROR')
        severity = kwargs.pop('severity', ErrorSeverity.MEDIUM)

        super().__init__(message, code=code, severity=severity, **kwargs)


class NotFoundError(RailGraphQLError):
    """Error for resource not found."""

    def __init__(self, message: str, resource_type: Optional[str] = None, **kwargs):
        code = kwargs.pop('code', 'NOT_FOUND')
        severity = kwargs.pop('severity', ErrorSeverity.LOW)

        extensions = kwargs.pop('extensions', {})
        if resource_type:
            extensions['resource_type'] = resource_type

        super().__init__(message, code=code, severity=severity, extensions=extensions, **kwargs)


class BusinessLogicError(RailGraphQLError):
    """Error for business logic violations."""

    def __init__(self, message: str, **kwargs):
        code = kwargs.pop('code', 'BUSINESS_LOGIC_ERROR')
        severity = kwargs.pop('severity', ErrorSeverity.MEDIUM)

        super().__init__(message, code=code, severity=severity, **kwargs)


class InternalError(RailGraphQLError):
    """Error for internal system errors."""

    def __init__(self, message: str = "Internal server error", **kwargs):
        code = kwargs.pop('code', 'INTERNAL_ERROR')
        severity = kwargs.pop('severity', ErrorSeverity.HIGH)

        super().__init__(message, code=code, severity=severity, **kwargs)


class RateLimitError(RailGraphQLError):
    """Error for rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", **kwargs):
        code = kwargs.pop('code', 'RATE_LIMIT_ERROR')
        severity = kwargs.pop('severity', ErrorSeverity.MEDIUM)

        super().__init__(message, code=code, severity=severity, **kwargs)


class ErrorHandler:
    """Handle and format GraphQL errors."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = ErrorHandlingSettings.from_schema(schema_name)

    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> RailGraphQLError:
        """
        Handle and convert exceptions to GraphQL errors.

        Args:
            error: Original exception
            context: Additional context information

        Returns:
            Formatted GraphQL error
        """
        context = context or {}

        # Log the error
        if self.settings.enable_error_logging:
            self._log_error(error, context)

        # Convert to appropriate GraphQL error
        graphql_error = self._convert_error(error, context)

        # Apply error formatting
        formatted_error = self._format_error(graphql_error, context)

        # Report error if enabled
        if self.settings.enable_error_reporting:
            self._report_error(formatted_error, context)

        return formatted_error

    def _convert_error(self, error: Exception, context: Dict[str, Any]) -> RailGraphQLError:
        """Convert exception to appropriate GraphQL error."""

        # Already a RailGraphQLError
        if isinstance(error, RailGraphQLError):
            return error

        # Django validation errors
        if isinstance(error, ValidationError):
            return ValidationError(str(error))

        # Django permission errors
        if isinstance(error, PermissionDenied):
            return AuthorizationError(str(error))

        # Database integrity errors
        if isinstance(error, IntegrityError):
            return BusinessLogicError("Data integrity constraint violated")

        # Permission errors
        if isinstance(error, PermissionError):
            return AuthorizationError(str(error))

        # Value errors (validation)
        if isinstance(error, ValueError):
            return ValidationError(str(error))

        # Generic GraphQL errors
        if isinstance(error, GraphQLError):
            return RailGraphQLError(str(error))

        # Unknown errors
        message = "Internal server error"
        if self.settings.enable_detailed_errors:
            message = str(error)

        return InternalError(message)

    def _format_error(self, error: RailGraphQLError, context: Dict[str, Any]) -> RailGraphQLError:
        """Format error for client response."""

        # Truncate message if too long
        message = error.message
        if len(message) > self.settings.max_error_message_length:
            message = message[:self.settings.max_error_message_length] + "..."

        # Prepare extensions
        extensions = dict(error.extensions or {})

        # Add error code prefix
        if 'code' in extensions and self.settings.error_code_prefix:
            extensions['code'] = f"{self.settings.error_code_prefix}_{extensions['code']}"

        # Add stack trace in development
        if self.settings.include_stack_trace and hasattr(error, '__traceback__'):
            extensions['stack_trace'] = traceback.format_exception(
                type(error), error, error.__traceback__
            )

        # Add context information
        if context:
            extensions['context'] = {
                'schema': self.schema_name,
                'timestamp': context.get('timestamp'),
                'user_id': context.get('user_id'),
                'request_id': context.get('request_id'),
            }

        # Create formatted error
        formatted_error = RailGraphQLError(
            message=message,
            code=error.code,
            severity=error.severity,
            extensions=extensions
        )

        return formatted_error

    def _log_error(self, error: Exception, context: Dict[str, Any]) -> None:
        """Log error with appropriate level."""

        # Determine log level
        log_level = getattr(logging, self.settings.log_level.upper(), logging.ERROR)

        # Prepare log message
        error_type = type(error).__name__
        error_message = str(error)

        log_message = f"GraphQL Error [{error_type}]: {error_message}"

        # Add context
        if context:
            log_message += f" (Context: {context})"

        # Log with stack trace for internal errors
        include_exc_info = isinstance(error, (InternalError, Exception)
                                      ) and not isinstance(error, RailGraphQLError)

        logger.log(log_level, log_message, exc_info=include_exc_info)

    def _report_error(self, error: RailGraphQLError, context: Dict[str, Any]) -> None:
        """Report error to external services."""

        # Only report high severity errors
        if error.severity not in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            return

        # Sentry integration
        if self.settings.enable_sentry_integration:
            try:
                import sentry_sdk

                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("graphql_schema", self.schema_name or "default")
                    scope.set_tag("error_code", error.code)
                    scope.set_level(error.severity.value)

                    # Add context
                    for key, value in context.items():
                        scope.set_extra(key, value)

                    sentry_sdk.capture_exception(error)

            except ImportError:
                logger.warning("Sentry SDK not available for error reporting")
            except Exception as e:
                logger.error(f"Failed to report error to Sentry: {e}")


class ErrorFormatter:
    """Format errors for GraphQL responses."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = ErrorHandlingSettings.from_schema(schema_name)
        self.error_handler = ErrorHandler(schema_name)

    def format_error(self, error: GraphQLError) -> Dict[str, Any]:
        """
        Format GraphQL error for response.

        Args:
            error: GraphQL error

        Returns:
            Formatted error dictionary
        """

        # Handle the error
        if not isinstance(error, RailGraphQLError):
            handled_error = self.error_handler.handle_error(error)
        else:
            handled_error = error

        # Build error response
        error_dict = {
            'message': handled_error.message,
        }

        # Add locations if available
        if hasattr(handled_error, 'locations') and handled_error.locations:
            error_dict['locations'] = [
                {'line': loc.line, 'column': loc.column}
                for loc in handled_error.locations
            ]

        # Add path if available
        if hasattr(handled_error, 'path') and handled_error.path:
            error_dict['path'] = handled_error.path

        # Add extensions
        if handled_error.extensions:
            error_dict['extensions'] = handled_error.extensions

        return error_dict

    def format_execution_result(self, result: ExecutionResult) -> Dict[str, Any]:
        """
        Format execution result with proper error handling.

        Args:
            result: GraphQL execution result

        Returns:
            Formatted result dictionary
        """

        response = {}

        # Add data
        if result.data is not None:
            response['data'] = result.data

        # Add errors
        if result.errors:
            response['errors'] = [
                self.format_error(error) for error in result.errors
            ]

        # Add extensions
        if hasattr(result, 'extensions') and result.extensions:
            response['extensions'] = result.extensions

        return response


# Global instances
error_handler = ErrorHandler()
error_formatter = ErrorFormatter()


def get_error_handler(schema_name: Optional[str] = None) -> ErrorHandler:
    """Get error handler instance for schema."""
    return ErrorHandler(schema_name)


def get_error_formatter(schema_name: Optional[str] = None) -> ErrorFormatter:
    """Get error formatter instance for schema."""
    return ErrorFormatter(schema_name)


def handle_graphql_error(error: Exception, schema_name: Optional[str] = None, **context) -> RailGraphQLError:
    """
    Handle GraphQL error with proper formatting and logging.

    Args:
        error: Exception to handle
        schema_name: Schema name (optional)
        **context: Additional context

    Returns:
        Formatted GraphQL error
    """
    handler = get_error_handler(schema_name)
    return handler.handle_error(error, context)
