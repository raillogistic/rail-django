"""
SystÃƒÂ¨me d'audit et de journalisation pour Django GraphQL.

Ce module fournit :
- Journalisation des ÃƒÂ©vÃƒÂ©nements de sÃƒÂ©curitÃƒÂ©
- Audit des accÃƒÂ¨s aux donnÃƒÂ©es
- TraÃƒÂ§abilitÃƒÂ© des modifications
- DÃƒÂ©tection d'anomalies
- Rapports de sÃƒÂ©curitÃƒÂ©
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from django.contrib.auth import get_user_model

# from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone as django_timezone
from graphql import GraphQLError, GraphQLResolveInfo

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _resolve_request(context: Any) -> Optional[Any]:
    if context is None:
        return None
    if hasattr(context, "META") and hasattr(context, "method"):
        return context
    request = getattr(context, "request", None)
    if request is not None:
        return request
    return None


def _resolve_user(context: Any, request: Any) -> Optional[Any]:
    user = getattr(context, "user", None)
    if user is not None:
        return user
    if request is not None:
        return getattr(request, "user", None)
    return None


def _snapshot_instance_fields(instance: models.Model) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for field in getattr(instance._meta, "concrete_fields", []):
        try:
            if field.is_relation and (field.many_to_one or field.one_to_one):
                snapshot[field.name] = getattr(instance, field.attname, None)
            else:
                snapshot[field.name] = getattr(instance, field.name, None)
        except Exception:
            snapshot[field.name] = None
    return snapshot


def _classify_exception(exc: Exception):
    message = str(exc).lower()
    if isinstance(exc, PermissionError):
        return AuditEventType.PERMISSION_DENIED, AuditSeverity.WARNING
    if "rate limit" in message:
        return AuditEventType.RATE_LIMIT_EXCEEDED, AuditSeverity.WARNING
    if "introspection" in message:
        return AuditEventType.INTROSPECTION_ATTEMPT, AuditSeverity.WARNING
    if "permission" in message or "authentication" in message or "not permitted" in message:
        return AuditEventType.PERMISSION_DENIED, AuditSeverity.WARNING
    return AuditEventType.SYSTEM_ERROR, AuditSeverity.ERROR


class AuditEventType(Enum):
    """Types d'ÃƒÂ©vÃƒÂ©nements d'audit."""

    # Authentification
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    MFA_SETUP = "mfa_setup"
    MFA_SUCCESS = "mfa_success"
    MFA_FAILURE = "mfa_failure"

    # Autorisation
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"

    # AccÃƒÂ¨s aux donnÃƒÂ©es
    DATA_ACCESS = "data_access"
    DATA_EXPORT = "data_export"
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"

    # Modifications
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_OPERATION = "bulk_operation"

    # SÃƒÂ©curitÃƒÂ©
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    INTROSPECTION_ATTEMPT = "introspection_attempt"

    # SystÃƒÂ¨me
    SYSTEM_ERROR = "system_error"
    CONFIGURATION_CHANGE = "configuration_change"
    SCHEMA_CHANGE = "schema_change"


class AuditSeverity(Enum):
    """Niveaux de gravitÃƒÂ© des ÃƒÂ©vÃƒÂ©nements d'audit."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Ãƒâ€°vÃƒÂ©nement d'audit."""

    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime
    user_id: Optional[int] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None

    # Contexte GraphQL
    operation_name: Optional[str] = None
    operation_type: Optional[str] = None
    query_hash: Optional[str] = None
    variables: Optional[dict[str, Any]] = None

    # DonnÃƒÂ©es affectÃƒÂ©es
    model_name: Optional[str] = None
    object_id: Optional[str] = None
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

    # MÃƒÂ©tadonnÃƒÂ©es
    message: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None

    # SÃƒÂ©curitÃƒÂ©
    risk_score: Optional[int] = None
    threat_indicators: Optional[list[str]] = None

    def __post_init__(self):
        """Initialise les valeurs par dÃƒÂ©faut."""
        if self.timestamp is None:
            self.timestamp = django_timezone.now()

        if self.tags is None:
            self.tags = []

        if self.details is None:
            self.details = {}

        if self.threat_indicators is None:
            self.threat_indicators = []


class AuditLogger:
    """
    Gestionnaire de journalisation d'audit.
    """

    def __init__(self):
        """Initialise le gestionnaire d'audit."""
        self.logger = logging.getLogger("audit")
        self._event_handlers = {}
        self._risk_calculators = {}

        # Configuration par dÃƒÂ©faut
        self.sensitive_fields = {
            "password",
            "token",
            "secret",
            "key",
            "hash",
            "ssn",
            "social_security",
            "credit_card",
            "bank_account",
            "email",
            "phone",
            "address",
        }

        self.high_risk_operations = {
            "delete",
            "bulk_delete",
            "user_delete",
            "permission_change",
            "role_change",
            "password_reset",
            "mfa_disable",
        }

        # Enregistrer les calculateurs de risque par dÃƒÂ©faut
        self._setup_default_risk_calculators()

    def _setup_default_risk_calculators(self):
        """Configure les calculateurs de risque par dÃƒÂ©faut."""
        self.register_risk_calculator(
            AuditEventType.LOGIN_FAILURE, self._calculate_login_failure_risk
        )

        self.register_risk_calculator(
            AuditEventType.PERMISSION_DENIED, self._calculate_permission_denied_risk
        )

        self.register_risk_calculator(
            AuditEventType.SENSITIVE_DATA_ACCESS, self._calculate_sensitive_data_risk
        )

    def log_event(self, event: AuditEvent):
        """
        Enregistre un ÃƒÂ©vÃƒÂ©nement d'audit.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement ÃƒÂ  enregistrer
        """
        # Calculer le score de risque si non fourni
        if event.risk_score is None:
            event.risk_score = self._calculate_risk_score(event)

        # Masquer les donnÃƒÂ©es sensibles
        sanitized_event = self._sanitize_event(event)

        # Enregistrer dans les logs
        log_data = _json_safe(asdict(sanitized_event))
        log_data["timestamp"] = sanitized_event.timestamp.isoformat()

        # Choisir le niveau de log appropriÃƒÂ©
        if event.severity == AuditSeverity.CRITICAL:
            self.logger.critical(json.dumps(log_data, cls=DjangoJSONEncoder))
        elif event.severity == AuditSeverity.ERROR:
            self.logger.error(json.dumps(log_data, cls=DjangoJSONEncoder))
        elif event.severity == AuditSeverity.WARNING:
            self.logger.warning(json.dumps(log_data, cls=DjangoJSONEncoder))
        else:
            self.logger.info(json.dumps(log_data, cls=DjangoJSONEncoder))

        # ExÃƒÂ©cuter les gestionnaires d'ÃƒÂ©vÃƒÂ©nements
        self._execute_event_handlers(sanitized_event)

        # DÃƒÂ©tecter les anomalies
        self._detect_anomalies(sanitized_event)

    def _sanitize_event(self, event: AuditEvent) -> AuditEvent:
        """
        Masque les donnÃƒÂ©es sensibles dans un ÃƒÂ©vÃƒÂ©nement.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement ÃƒÂ  masquer

        Returns:
            Ãƒâ€°vÃƒÂ©nement masquÃƒÂ©
        """
        sanitized = AuditEvent(**asdict(event))

        if sanitized.old_value is not None:
            sanitized.old_value = self._mask_sensitive_payload(sanitized.old_value)
        if sanitized.new_value is not None:
            sanitized.new_value = self._mask_sensitive_payload(sanitized.new_value)

        # Masquer les valeurs sensibles
        if (
            sanitized.field_name
            and sanitized.field_name.lower() in self.sensitive_fields
        ):
            if sanitized.old_value:
                sanitized.old_value = "***MASKED***"
            if sanitized.new_value:
                sanitized.new_value = "***MASKED***"

        # Masquer les variables sensibles
        if sanitized.variables:
            sanitized.variables = self._mask_sensitive_variables(sanitized.variables)

        # Masquer les dÃƒÂ©tails sensibles
        if sanitized.details:
            sanitized.details = self._mask_sensitive_details(sanitized.details)

        return sanitized

    def _mask_sensitive_variables(self, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Masque les variables sensibles.

        Args:
            variables: Variables ÃƒÂ  masquer

        Returns:
            Variables masquÃƒÂ©es
        """
        masked = {}
        for key, value in variables.items():
            if key.lower() in self.sensitive_fields:
                masked[key] = "***MASKED***"
            elif isinstance(value, dict):
                masked[key] = self._mask_sensitive_variables(value)
            elif isinstance(value, list):
                masked[key] = [
                    self._mask_sensitive_variables(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                masked[key] = value
        return masked

    def _mask_sensitive_details(self, details: dict[str, Any]) -> dict[str, Any]:
        """
        Masque les dÃƒÂ©tails sensibles.

        Args:
            details: DÃƒÂ©tails ÃƒÂ  masquer

        Returns:
            DÃƒÂ©tails masquÃƒÂ©s
        """
        return self._mask_sensitive_variables(details)

    def _mask_sensitive_payload(self, payload: Any) -> Any:
        if isinstance(payload, (dict, list)):
            return self._mask_sensitive_variables(payload)
        return payload

    def _calculate_risk_score(self, event: AuditEvent) -> int:
        """
        Calcule le score de risque d'un ÃƒÂ©vÃƒÂ©nement.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement ÃƒÂ  ÃƒÂ©valuer

        Returns:
            Score de risque (0-100)
        """
        # Utiliser un calculateur spÃƒÂ©cifique si disponible
        if event.event_type in self._risk_calculators:
            return self._risk_calculators[event.event_type](event)

        # Calcul par dÃƒÂ©faut
        base_score = 0

        # Score basÃƒÂ© sur la gravitÃƒÂ©
        severity_scores = {
            AuditSeverity.INFO: 10,
            AuditSeverity.WARNING: 30,
            AuditSeverity.ERROR: 60,
            AuditSeverity.CRITICAL: 90,
        }
        base_score += severity_scores.get(event.severity, 10)

        # Score basÃƒÂ© sur le type d'ÃƒÂ©vÃƒÂ©nement
        if event.event_type in [
            AuditEventType.LOGIN_FAILURE,
            AuditEventType.PERMISSION_DENIED,
            AuditEventType.SECURITY_VIOLATION,
        ]:
            base_score += 20

        # Score basÃƒÂ© sur l'accÃƒÂ¨s aux donnÃƒÂ©es sensibles
        if event.field_name and event.field_name.lower() in self.sensitive_fields:
            base_score += 15

        # Score basÃƒÂ© sur les opÃƒÂ©rations ÃƒÂ  haut risque
        if (
            event.operation_name
            and event.operation_name.lower() in self.high_risk_operations
        ):
            base_score += 25

        return min(base_score, 100)

    def _calculate_login_failure_risk(self, event: AuditEvent) -> int:
        """
        Calcule le risque pour les ÃƒÂ©checs de connexion.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement d'ÃƒÂ©chec de connexion

        Returns:
            Score de risque
        """
        base_score = 30

        # VÃƒÂ©rifier les tentatives rÃƒÂ©pÃƒÂ©tÃƒÂ©es
        if event.ip_address:
            # Cette logique devrait ÃƒÂªtre implÃƒÂ©mentÃƒÂ©e avec un cache ou une base de donnÃƒÂ©es
            # pour compter les tentatives rÃƒÂ©centes
            pass

        return base_score

    def _calculate_permission_denied_risk(self, event: AuditEvent) -> int:
        """
        Calcule le risque pour les refus de permission.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement de refus de permission

        Returns:
            Score de risque
        """
        base_score = 40

        # Augmenter le score pour les tentatives d'accÃƒÂ¨s ÃƒÂ  des donnÃƒÂ©es sensibles
        if event.field_name and event.field_name.lower() in self.sensitive_fields:
            base_score += 20

        return base_score

    def _calculate_sensitive_data_risk(self, event: AuditEvent) -> int:
        """
        Calcule le risque pour l'accÃƒÂ¨s aux donnÃƒÂ©es sensibles.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement d'accÃƒÂ¨s aux donnÃƒÂ©es sensibles

        Returns:
            Score de risque
        """
        base_score = 50

        # Augmenter le score pour certains types de donnÃƒÂ©es
        if event.field_name:
            field_lower = event.field_name.lower()
            if any(
                sensitive in field_lower
                for sensitive in ["password", "token", "secret"]
            ):
                base_score += 30
            elif any(
                sensitive in field_lower for sensitive in ["ssn", "credit_card", "bank"]
            ):
                base_score += 25

        return base_score

    def register_risk_calculator(
        self, event_type: AuditEventType, calculator: callable
    ):
        """
        Enregistre un calculateur de risque personnalisÃƒÂ©.

        Args:
            event_type: Type d'ÃƒÂ©vÃƒÂ©nement
            calculator: Fonction de calcul du risque
        """
        self._risk_calculators[event_type] = calculator

    def register_event_handler(self, event_type: AuditEventType, handler: callable):
        """
        Enregistre un gestionnaire d'ÃƒÂ©vÃƒÂ©nement.

        Args:
            event_type: Type d'ÃƒÂ©vÃƒÂ©nement
            handler: Fonction de gestion
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def _execute_event_handlers(self, event: AuditEvent):
        """
        ExÃƒÂ©cute les gestionnaires d'ÃƒÂ©vÃƒÂ©nements.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement ÃƒÂ  traiter
        """
        handlers = self._event_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Erreur dans le gestionnaire d'ÃƒÂ©vÃƒÂ©nement: {e}")

    def _detect_anomalies(self, event: AuditEvent):
        """
        DÃƒÂ©tecte les anomalies dans les ÃƒÂ©vÃƒÂ©nements.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement ÃƒÂ  analyser
        """
        # DÃƒÂ©tecter les tentatives de connexion suspectes
        if event.event_type == AuditEventType.LOGIN_FAILURE:
            self._detect_brute_force_attempts(event)

        # DÃƒÂ©tecter les accÃƒÂ¨s anormaux aux donnÃƒÂ©es
        if event.event_type == AuditEventType.SENSITIVE_DATA_ACCESS:
            self._detect_unusual_data_access(event)

        # DÃƒÂ©tecter les violations de sÃƒÂ©curitÃƒÂ© rÃƒÂ©pÃƒÂ©tÃƒÂ©es
        if event.event_type == AuditEventType.SECURITY_VIOLATION:
            self._detect_repeated_violations(event)

    def _detect_brute_force_attempts(self, event: AuditEvent):
        """
        DÃƒÂ©tecte les tentatives de force brute.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement d'ÃƒÂ©chec de connexion
        """
        # Cette logique devrait ÃƒÂªtre implÃƒÂ©mentÃƒÂ©e avec un systÃƒÂ¨me de cache
        # pour compter les tentatives par IP/utilisateur
        pass

    def _detect_unusual_data_access(self, event: AuditEvent):
        """
        DÃƒÂ©tecte les accÃƒÂ¨s inhabituels aux donnÃƒÂ©es.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement d'accÃƒÂ¨s aux donnÃƒÂ©es
        """
        # Analyser les patterns d'accÃƒÂ¨s habituels de l'utilisateur
        pass

    def _detect_repeated_violations(self, event: AuditEvent):
        """
        DÃƒÂ©tecte les violations rÃƒÂ©pÃƒÂ©tÃƒÂ©es.

        Args:
            event: Ãƒâ€°vÃƒÂ©nement de violation
        """
        # Compter les violations rÃƒÂ©centes du mÃƒÂªme utilisateur
        pass


def audit_graphql_operation(operation_type: str = None):
    """
    DÃƒÂ©corateur pour auditer les opÃƒÂ©rations GraphQL.

    Args:
        operation_type: Type d'opÃƒÂ©ration (optionnel)

    Returns:
        DÃƒÂ©corateur d'audit
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extraire le contexte GraphQL
            info = None
            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                    break

            if not info:
                return func(*args, **kwargs)

            context = getattr(info, "context", None)
            request = _resolve_request(context)
            user = _resolve_user(context, request)

            op_value = None
            if info.operation and getattr(info.operation, "operation", None):
                op_value = info.operation.operation.value

            gql_operation_name = None
            if info.operation and getattr(info.operation, "name", None):
                gql_operation_name = getattr(info.operation.name, "value", None)

            details = {}
            schema_name = getattr(context, "schema_name", None)
            if schema_name:
                details["schema_name"] = schema_name
            if gql_operation_name:
                details["operation_name"] = gql_operation_name
            if request is not None:
                details["request_path"] = getattr(request, "path", None)
                details["request_method"] = getattr(request, "method", None)

            session_id = None
            if request is not None and hasattr(request, "session"):
                session_id = getattr(request.session, "session_key", None)

            event = AuditEvent(
                event_type=AuditEventType.DATA_ACCESS,
                severity=AuditSeverity.INFO,
                timestamp=django_timezone.now(),
                user_id=user.id if user and user.is_authenticated else None,
                username=user.username if user and user.is_authenticated else None,
                ip_address=get_client_ip(request) if request else None,
                user_agent=request.META.get("HTTP_USER_AGENT") if request else None,
                session_id=session_id,
                operation_name=info.field_name,
                operation_type=operation_type or op_value,
                query_hash=hash_query(info.operation) if info.operation else None,
                variables=info.variable_values,
                details=details or None,
            )

            try:
                result = func(*args, **kwargs)

                # Auditer le succÃƒÂ¨s
                audit_logger.log_event(event)

                return result

            except Exception as e:
                event.event_type, event.severity = _classify_exception(e)
                event.message = str(e)
                if isinstance(e, GraphQLError):
                    error_code = (getattr(e, "extensions", {}) or {}).get("code")
                    if error_code:
                        event.details = dict(event.details or {})
                        event.details["error_code"] = str(error_code)
                event.details = dict(event.details or {})
                event.details["error_type"] = e.__class__.__name__
                audit_logger.log_event(event)

                raise

        return wrapper

    return decorator


def audit_data_modification(model_class: type, operation: str):
    """
    Decorator to audit data modifications.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            info = None
            instance = None

            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                elif isinstance(arg, model_class):
                    instance = arg

            context = getattr(info, "context", None) if info else None
            request = _resolve_request(context)
            user = _resolve_user(context, request)

            old_values = None
            if instance and operation in ["update", "delete"]:
                old_values = _snapshot_instance_fields(instance)

            try:
                result = func(*args, **kwargs)

                if instance is None and isinstance(result, model_class):
                    instance = result

                new_values = None
                if instance and operation in ["create", "update"]:
                    new_values = _snapshot_instance_fields(instance)

                details = {"operation": operation, "model": model_class.__name__}
                schema_name = getattr(context, "schema_name", None)
                if schema_name:
                    details["schema_name"] = schema_name
                if request is not None:
                    details["request_path"] = getattr(request, "path", None)
                    details["request_method"] = getattr(request, "method", None)

                session_id = None
                if request is not None and hasattr(request, "session"):
                    session_id = getattr(request.session, "session_key", None)

                event_type_map = {
                    "create": AuditEventType.CREATE,
                    "update": AuditEventType.UPDATE,
                    "delete": AuditEventType.DELETE,
                }

                event = AuditEvent(
                    event_type=event_type_map.get(operation, AuditEventType.DATA_ACCESS),
                    severity=AuditSeverity.INFO,
                    timestamp=django_timezone.now(),
                    user_id=user.id if user and user.is_authenticated else None,
                    username=user.username if user and user.is_authenticated else None,
                    ip_address=get_client_ip(request) if request else None,
                    user_agent=request.META.get("HTTP_USER_AGENT") if request else None,
                    session_id=session_id,
                    model_name=model_class.__name__,
                    object_id=str(instance.pk) if instance and hasattr(instance, "pk") else None,
                    old_value=old_values,
                    new_value=new_values,
                    details=details,
                )

                audit_logger.log_event(event)

                return result

            except Exception as e:
                event_type, severity = _classify_exception(e)
                session_id = None
                if request is not None and hasattr(request, "session"):
                    session_id = getattr(request.session, "session_key", None)
                error_details = {"operation": operation, "error": str(e), "error_type": e.__class__.__name__}
                schema_name = getattr(context, "schema_name", None)
                if schema_name:
                    error_details["schema_name"] = schema_name
                if request is not None:
                    error_details["request_path"] = getattr(request, "path", None)
                    error_details["request_method"] = getattr(request, "method", None)

                event = AuditEvent(
                    event_type=event_type,
                    severity=severity,
                    timestamp=django_timezone.now(),
                    user_id=user.id if user and user.is_authenticated else None,
                    username=user.username if user and user.is_authenticated else None,
                    ip_address=get_client_ip(request) if request else None,
                    user_agent=request.META.get("HTTP_USER_AGENT") if request else None,
                    session_id=session_id,
                    model_name=model_class.__name__,
                    message=f"Error during {operation}: {str(e)}",
                    details=error_details,
                )

                audit_logger.log_event(event)

                raise

        return wrapper

    return decorator


def get_client_ip(request) -> Optional[str]:
    """
    RÃƒÂ©cupÃƒÂ¨re l'adresse IP du client.

    Args:
        request: RequÃƒÂªte HTTP

    Returns:
        Adresse IP du client
    """
    if not request:
        return None

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")

    return ip


def hash_query(operation) -> str:
    """
    GÃƒÂ©nÃƒÂ¨re un hash pour une opÃƒÂ©ration GraphQL.

    Args:
        operation: OpÃƒÂ©ration GraphQL

    Returns:
        Hash de l'opÃƒÂ©ration
    """
    if not operation:
        return ""

    query_string = str(operation)
    return hashlib.sha256(query_string.encode()).hexdigest()[:16]


# Instance globale du gestionnaire d'audit
audit_logger = AuditLogger()
