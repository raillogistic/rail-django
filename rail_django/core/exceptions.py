"""
Custom GraphQL error handling and exception classes for Django GraphQL Auto-Generation.

This module provides comprehensive error handling with structured error responses,
proper error codes, and detailed debugging information for development.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from graphql import GraphQLError

logger = logging.getLogger(__name__)


class ErrorCode(Enum):
    """Codes d'erreur standardisés pour GraphQL."""

    # Erreurs génériques
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

    # Erreurs de validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    FIELD_VALIDATION_ERROR = "FIELD_VALIDATION_ERROR"
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
    INVALID_INPUT_FORMAT = "INVALID_INPUT_FORMAT"

    # Erreurs d'authentification et autorisation
    authentication_required = "authentication_required"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"

    # Erreurs de ressources
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"
    RESOURCE_LOCKED = "RESOURCE_LOCKED"
    RESOURCE_DELETED = "RESOURCE_DELETED"

    # Erreurs de sécurité
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    SQL_INJECTION_DETECTED = "SQL_INJECTION_DETECTED"
    XSS_ATTACK_DETECTED = "XSS_ATTACK_DETECTED"
    MALICIOUS_INPUT_DETECTED = "MALICIOUS_INPUT_DETECTED"

    # Erreurs de limitation
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    QUERY_COMPLEXITY_EXCEEDED = "QUERY_COMPLEXITY_EXCEEDED"
    QUERY_DEPTH_EXCEEDED = "QUERY_DEPTH_EXCEEDED"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"

    # Erreurs de configuration
    SCHEMA_ERROR = "SCHEMA_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    FEATURE_DISABLED = "FEATURE_DISABLED"

    # Erreurs de fichiers
    FILE_UPLOAD_ERROR = "FILE_UPLOAD_ERROR"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    VIRUS_DETECTED = "VIRUS_DETECTED"


class GraphQLAutoError(GraphQLError):
    """Classe de base pour toutes les erreurs GraphQL personnalisées."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        field: str = None,
        details: Dict[str, Any] = None,
        path: List[Union[str, int]] = None,
        locations: List[Dict[str, int]] = None,
        original_error: Exception = None,
    ):
        """
        Initialise une erreur GraphQL personnalisée.

        Args:
            message: Message d'erreur lisible par l'utilisateur
            code: Code d'erreur standardisé
            field: Nom du champ concerné (optionnel)
            details: Détails supplémentaires sur l'erreur
            path: Chemin GraphQL où l'erreur s'est produite
            locations: Emplacements dans la requête GraphQL
            original_error: Exception originale qui a causé cette erreur
        """
        error_kwargs: Dict[str, Any] = {}
        if path is not None:
            error_kwargs["path"] = path
        if original_error is not None:
            error_kwargs["original_error"] = original_error
        super().__init__(message, **error_kwargs)

        self.code = code
        self.field = field
        self.details = details or {}
        self.original_error = original_error

        # Ajout des extensions GraphQL
        self.extensions = {
            "code": code.value,
            "field": field,
            "details": self.details,
        }

        # Ajout d'informations de débogage en mode développement
        if settings.DEBUG and original_error:
            self.extensions["debug"] = {
                "original_error": str(original_error),
                "error_type": type(original_error).__name__,
            }


class ValidationError(GraphQLAutoError):
    """Erreur de validation des données d'entrée."""

    def __init__(
        self,
        message: str = "Erreur de validation",
        field: str = None,
        validation_errors: Dict[str, List[str]] = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if validation_errors:
            details["validation_errors"] = validation_errors

        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            field=field,
            details=details,
            **kwargs,
        )


class AuthenticationError(GraphQLAutoError):
    """Erreur d'authentification."""

    def __init__(self, message: str = "Authentification requise", **kwargs):
        super().__init__(
            message=message, code=ErrorCode.authentication_required, **kwargs
        )


class PermissionError(GraphQLAutoError):
    """Erreur de permissions."""

    def __init__(
        self,
        message: str = "Permission refusée",
        required_permission: str = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if required_permission:
            details["required_permission"] = required_permission

        super().__init__(
            message=message, code=ErrorCode.PERMISSION_DENIED, details=details, **kwargs
        )


class ResourceNotFoundError(GraphQLAutoError):
    """Erreur de ressource non trouvée."""

    def __init__(
        self,
        message: str = "Ressource non trouvée",
        resource_type: str = None,
        resource_id: str = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            message=message,
            code=ErrorCode.RESOURCE_NOT_FOUND,
            details=details,
            **kwargs,
        )


class SecurityError(GraphQLAutoError):
    """Erreur de sécurité détectée."""

    def __init__(
        self,
        message: str = "Violation de sécurité détectée",
        threat_type: str = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if threat_type:
            details["threat_type"] = threat_type

        super().__init__(
            message=message,
            code=ErrorCode.SECURITY_VIOLATION,
            details=details,
            **kwargs,
        )


class RateLimitError(GraphQLAutoError):
    """Erreur de limitation de taux."""

    def __init__(
        self,
        message: str = "Limite de taux dépassée",
        retry_after: int = None,
        limit: int = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if retry_after:
            details["retry_after"] = retry_after
        if limit:
            details["limit"] = limit

        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            details=details,
            **kwargs,
        )


class QueryComplexityError(GraphQLAutoError):
    """Erreur de complexité de requête."""

    def __init__(
        self,
        message: str = "Complexité de requête dépassée",
        complexity: int = None,
        max_complexity: int = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if complexity:
            details["complexity"] = complexity
        if max_complexity:
            details["max_complexity"] = max_complexity

        super().__init__(
            message=message,
            code=ErrorCode.QUERY_COMPLEXITY_EXCEEDED,
            details=details,
            **kwargs,
        )


class QueryDepthError(GraphQLAutoError):
    """Erreur de profondeur de requête."""

    def __init__(
        self,
        message: str = "Profondeur de requête dépassée",
        depth: int = None,
        max_depth: int = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if depth:
            details["depth"] = depth
        if max_depth:
            details["max_depth"] = max_depth

        super().__init__(
            message=message,
            code=ErrorCode.QUERY_DEPTH_EXCEEDED,
            details=details,
            **kwargs,
        )


class FileUploadError(GraphQLAutoError):
    """Erreur de téléchargement de fichier."""

    def __init__(
        self,
        message: str = "Erreur de téléchargement de fichier",
        file_name: str = None,
        file_size: int = None,
        max_size: int = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if file_name:
            details["file_name"] = file_name
        if file_size:
            details["file_size"] = file_size
        if max_size:
            details["max_size"] = max_size

        super().__init__(
            message=message, code=ErrorCode.FILE_UPLOAD_ERROR, details=details, **kwargs
        )


class ErrorHandler:
    """Gestionnaire d'erreurs centralisé pour GraphQL."""

    def __init__(self):
        self.logger = logging.getLogger("rail_django.errors")

    def handle_error(
        self, error: Exception, context: Any = None, field_name: str = None
    ) -> GraphQLAutoError:
        """
        Gère et convertit les erreurs en erreurs GraphQL appropriées.

        Args:
            error: Exception à traiter
            context: Contexte GraphQL (info.context)
            field_name: Nom du champ où l'erreur s'est produite

        Returns:
            GraphQLAutoError: Erreur GraphQL formatée
        """
        # Log de l'erreur
        self._log_error(error, context, field_name)

        # Conversion des erreurs Django
        if isinstance(error, DjangoValidationError):
            return self._handle_django_validation_error(error, field_name)
        elif isinstance(error, DjangoPermissionDenied):
            return self._handle_django_permission_error(error)
        elif isinstance(error, ObjectDoesNotExist):
            return self._handle_not_found_error(error)

        # Erreurs GraphQL personnalisées (déjà formatées)
        elif isinstance(error, GraphQLAutoError):
            return error

        # Erreurs génériques
        else:
            return self._handle_generic_error(error, field_name)

    def _log_error(self, error: Exception, context: Any = None, field_name: str = None):
        """Log l'erreur avec le contexte approprié."""
        extra_data = {
            "error_type": type(error).__name__,
            "field_name": field_name,
        }

        if context and hasattr(context, "user"):
            extra_data["user"] = getattr(context.user, "username", "anonymous")

        self.logger.error(
            f"GraphQL Error in field '{field_name}': {str(error)}",
            extra=extra_data,
            exc_info=True,
        )

    def _handle_django_validation_error(
        self, error: DjangoValidationError, field_name: str = None
    ) -> ValidationError:
        """Gère les erreurs de validation Django."""
        if hasattr(error, "message_dict"):
            # Erreurs de validation de formulaire
            return ValidationError(
                message="Erreurs de validation détectées",
                field=field_name,
                validation_errors=error.message_dict,
                original_error=error,
            )
        else:
            # Erreur de validation simple
            return ValidationError(
                message=str(error), field=field_name, original_error=error
            )

    def _handle_django_permission_error(
        self, error: DjangoPermissionDenied
    ) -> PermissionError:
        """Gère les erreurs de permission Django."""
        return PermissionError(
            message=str(error) or "Permission refusée", original_error=error
        )

    def _handle_not_found_error(
        self, error: ObjectDoesNotExist
    ) -> ResourceNotFoundError:
        """Gère les erreurs de ressource non trouvée."""
        return ResourceNotFoundError(
            message="La ressource demandée n'existe pas", original_error=error
        )

    def _handle_generic_error(
        self, error: Exception, field_name: str = None
    ) -> GraphQLAutoError:
        """Gère les erreurs génériques."""
        if settings.DEBUG:
            # En mode debug, exposer les détails de l'erreur
            return GraphQLAutoError(
                message=f"Erreur interne: {str(error)}",
                code=ErrorCode.INTERNAL_ERROR,
                field=field_name,
                details={"debug_info": str(error)},
                original_error=error,
            )
        else:
            # En production, message générique
            return GraphQLAutoError(
                message="Une erreur interne s'est produite",
                code=ErrorCode.INTERNAL_ERROR,
                field=field_name,
                original_error=error,
            )


# Instance globale du gestionnaire d'erreurs
error_handler = ErrorHandler()


def handle_graphql_error(
    error: Exception, context: Any = None, field_name: str = None
) -> GraphQLAutoError:
    """
    Fonction utilitaire pour gérer les erreurs GraphQL.

    Args:
        error: Exception à traiter
        context: Contexte GraphQL
        field_name: Nom du champ

    Returns:
        GraphQLAutoError: Erreur formatée
    """
    return error_handler.handle_error(error, context, field_name)
