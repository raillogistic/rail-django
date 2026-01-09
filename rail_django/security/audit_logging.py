"""
Système d'audit et de journalisation pour Django GraphQL.

Ce module fournit :
- Journalisation des événements de sécurité
- Audit des accès aux données
- Traçabilité des modifications
- Détection d'anomalies
- Rapports de sécurité
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


class AuditEventType(Enum):
    """Types d'événements d'audit."""

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

    # Accès aux données
    DATA_ACCESS = "data_access"
    DATA_EXPORT = "data_export"
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"

    # Modifications
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_OPERATION = "bulk_operation"

    # Sécurité
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    INTROSPECTION_ATTEMPT = "introspection_attempt"

    # Système
    SYSTEM_ERROR = "system_error"
    CONFIGURATION_CHANGE = "configuration_change"
    SCHEMA_CHANGE = "schema_change"


class AuditSeverity(Enum):
    """Niveaux de gravité des événements d'audit."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Événement d'audit."""

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
    variables: Optional[Dict[str, Any]] = None

    # Données affectées
    model_name: Optional[str] = None
    object_id: Optional[str] = None
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

    # Métadonnées
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None

    # Sécurité
    risk_score: Optional[int] = None
    threat_indicators: Optional[List[str]] = None

    def __post_init__(self):
        """Initialise les valeurs par défaut."""
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

        # Configuration par défaut
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

        # Enregistrer les calculateurs de risque par défaut
        self._setup_default_risk_calculators()

    def _setup_default_risk_calculators(self):
        """Configure les calculateurs de risque par défaut."""
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
        Enregistre un événement d'audit.

        Args:
            event: Événement à enregistrer
        """
        # Calculer le score de risque si non fourni
        if event.risk_score is None:
            event.risk_score = self._calculate_risk_score(event)

        # Masquer les données sensibles
        sanitized_event = self._sanitize_event(event)

        # Enregistrer dans les logs
        log_data = asdict(sanitized_event)
        log_data["timestamp"] = sanitized_event.timestamp.isoformat()

        # Choisir le niveau de log approprié
        if event.severity == AuditSeverity.CRITICAL:
            self.logger.critical(json.dumps(log_data, cls=DjangoJSONEncoder))
        elif event.severity == AuditSeverity.ERROR:
            self.logger.error(json.dumps(log_data, cls=DjangoJSONEncoder))
        elif event.severity == AuditSeverity.WARNING:
            self.logger.warning(json.dumps(log_data, cls=DjangoJSONEncoder))
        else:
            self.logger.info(json.dumps(log_data, cls=DjangoJSONEncoder))

        # Exécuter les gestionnaires d'événements
        self._execute_event_handlers(sanitized_event)

        # Détecter les anomalies
        self._detect_anomalies(sanitized_event)

    def _sanitize_event(self, event: AuditEvent) -> AuditEvent:
        """
        Masque les données sensibles dans un événement.

        Args:
            event: Événement à masquer

        Returns:
            Événement masqué
        """
        sanitized = AuditEvent(**asdict(event))

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

        # Masquer les détails sensibles
        if sanitized.details:
            sanitized.details = self._mask_sensitive_details(sanitized.details)

        return sanitized

    def _mask_sensitive_variables(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Masque les variables sensibles.

        Args:
            variables: Variables à masquer

        Returns:
            Variables masquées
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

    def _mask_sensitive_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Masque les détails sensibles.

        Args:
            details: Détails à masquer

        Returns:
            Détails masqués
        """
        return self._mask_sensitive_variables(details)

    def _calculate_risk_score(self, event: AuditEvent) -> int:
        """
        Calcule le score de risque d'un événement.

        Args:
            event: Événement à évaluer

        Returns:
            Score de risque (0-100)
        """
        # Utiliser un calculateur spécifique si disponible
        if event.event_type in self._risk_calculators:
            return self._risk_calculators[event.event_type](event)

        # Calcul par défaut
        base_score = 0

        # Score basé sur la gravité
        severity_scores = {
            AuditSeverity.INFO: 10,
            AuditSeverity.WARNING: 30,
            AuditSeverity.ERROR: 60,
            AuditSeverity.CRITICAL: 90,
        }
        base_score += severity_scores.get(event.severity, 10)

        # Score basé sur le type d'événement
        if event.event_type in [
            AuditEventType.LOGIN_FAILURE,
            AuditEventType.PERMISSION_DENIED,
            AuditEventType.SECURITY_VIOLATION,
        ]:
            base_score += 20

        # Score basé sur l'accès aux données sensibles
        if event.field_name and event.field_name.lower() in self.sensitive_fields:
            base_score += 15

        # Score basé sur les opérations à haut risque
        if (
            event.operation_name
            and event.operation_name.lower() in self.high_risk_operations
        ):
            base_score += 25

        return min(base_score, 100)

    def _calculate_login_failure_risk(self, event: AuditEvent) -> int:
        """
        Calcule le risque pour les échecs de connexion.

        Args:
            event: Événement d'échec de connexion

        Returns:
            Score de risque
        """
        base_score = 30

        # Vérifier les tentatives répétées
        if event.ip_address:
            # Cette logique devrait être implémentée avec un cache ou une base de données
            # pour compter les tentatives récentes
            pass

        return base_score

    def _calculate_permission_denied_risk(self, event: AuditEvent) -> int:
        """
        Calcule le risque pour les refus de permission.

        Args:
            event: Événement de refus de permission

        Returns:
            Score de risque
        """
        base_score = 40

        # Augmenter le score pour les tentatives d'accès à des données sensibles
        if event.field_name and event.field_name.lower() in self.sensitive_fields:
            base_score += 20

        return base_score

    def _calculate_sensitive_data_risk(self, event: AuditEvent) -> int:
        """
        Calcule le risque pour l'accès aux données sensibles.

        Args:
            event: Événement d'accès aux données sensibles

        Returns:
            Score de risque
        """
        base_score = 50

        # Augmenter le score pour certains types de données
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
        Enregistre un calculateur de risque personnalisé.

        Args:
            event_type: Type d'événement
            calculator: Fonction de calcul du risque
        """
        self._risk_calculators[event_type] = calculator

    def register_event_handler(self, event_type: AuditEventType, handler: callable):
        """
        Enregistre un gestionnaire d'événement.

        Args:
            event_type: Type d'événement
            handler: Fonction de gestion
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def _execute_event_handlers(self, event: AuditEvent):
        """
        Exécute les gestionnaires d'événements.

        Args:
            event: Événement à traiter
        """
        handlers = self._event_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Erreur dans le gestionnaire d'événement: {e}")

    def _detect_anomalies(self, event: AuditEvent):
        """
        Détecte les anomalies dans les événements.

        Args:
            event: Événement à analyser
        """
        # Détecter les tentatives de connexion suspectes
        if event.event_type == AuditEventType.LOGIN_FAILURE:
            self._detect_brute_force_attempts(event)

        # Détecter les accès anormaux aux données
        if event.event_type == AuditEventType.SENSITIVE_DATA_ACCESS:
            self._detect_unusual_data_access(event)

        # Détecter les violations de sécurité répétées
        if event.event_type == AuditEventType.SECURITY_VIOLATION:
            self._detect_repeated_violations(event)

    def _detect_brute_force_attempts(self, event: AuditEvent):
        """
        Détecte les tentatives de force brute.

        Args:
            event: Événement d'échec de connexion
        """
        # Cette logique devrait être implémentée avec un système de cache
        # pour compter les tentatives par IP/utilisateur
        pass

    def _detect_unusual_data_access(self, event: AuditEvent):
        """
        Détecte les accès inhabituels aux données.

        Args:
            event: Événement d'accès aux données
        """
        # Analyser les patterns d'accès habituels de l'utilisateur
        pass

    def _detect_repeated_violations(self, event: AuditEvent):
        """
        Détecte les violations répétées.

        Args:
            event: Événement de violation
        """
        # Compter les violations récentes du même utilisateur
        pass


def audit_graphql_operation(operation_type: str = None):
    """
    Décorateur pour auditer les opérations GraphQL.

    Args:
        operation_type: Type d'opération (optionnel)

    Returns:
        Décorateur d'audit
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

            user = getattr(info.context, "user", None)
            request = getattr(info.context, "request", None)

            # Créer l'événement d'audit
            event = AuditEvent(
                event_type=AuditEventType.DATA_ACCESS,
                severity=AuditSeverity.INFO,
                timestamp=django_timezone.now(),
                user_id=user.id if user and user.is_authenticated else None,
                username=user.username if user and user.is_authenticated else None,
                ip_address=get_client_ip(request) if request else None,
                user_agent=request.META.get("HTTP_USER_AGENT") if request else None,
                operation_name=info.field_name,
                operation_type=operation_type or info.operation.operation.value,
                query_hash=hash_query(info.operation) if info.operation else None,
                variables=info.variable_values,
            )

            try:
                result = func(*args, **kwargs)

                # Auditer le succès
                audit_logger.log_event(event)

                return result

            except Exception as e:
                # Auditer l'échec
                event.event_type = AuditEventType.SYSTEM_ERROR
                event.severity = AuditSeverity.ERROR
                event.message = str(e)
                audit_logger.log_event(event)

                raise

        return wrapper

    return decorator


def audit_data_modification(model_class: type, operation: str):
    """
    Décorateur pour auditer les modifications de données.

    Args:
        model_class: Classe du modèle
        operation: Type d'opération (create, update, delete)

    Returns:
        Décorateur d'audit
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extraire le contexte
            info = None
            instance = None

            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                elif isinstance(arg, model_class):
                    instance = arg

            user = getattr(info.context, "user", None) if info else None
            request = getattr(info.context, "request", None) if info else None

            # Capturer l'état avant modification
            old_values = {}
            if instance and operation in ["update", "delete"]:
                for field in model_class._meta.get_fields():
                    if hasattr(instance, field.name):
                        old_values[field.name] = getattr(instance, field.name)

            try:
                result = func(*args, **kwargs)

                # Capturer l'état après modification
                new_values = {}
                if instance and operation in ["create", "update"]:
                    for field in model_class._meta.get_fields():
                        if hasattr(instance, field.name):
                            new_values[field.name] = getattr(instance, field.name)

                # Créer l'événement d'audit
                event_type_map = {
                    "create": AuditEventType.CREATE,
                    "update": AuditEventType.UPDATE,
                    "delete": AuditEventType.DELETE,
                }

                event = AuditEvent(
                    event_type=event_type_map.get(
                        operation, AuditEventType.DATA_ACCESS
                    ),
                    severity=AuditSeverity.INFO,
                    timestamp=django_timezone.now(),
                    user_id=user.id if user and user.is_authenticated else None,
                    username=user.username if user and user.is_authenticated else None,
                    ip_address=get_client_ip(request) if request else None,
                    model_name=model_class.__name__,
                    object_id=str(instance.pk)
                    if instance and hasattr(instance, "pk")
                    else None,
                    old_value=old_values if old_values else None,
                    new_value=new_values if new_values else None,
                    details={"operation": operation, "model": model_class.__name__},
                )

                audit_logger.log_event(event)

                return result

            except Exception as e:
                # Auditer l'échec
                event = AuditEvent(
                    event_type=AuditEventType.SYSTEM_ERROR,
                    severity=AuditSeverity.ERROR,
                    timestamp=django_timezone.now(),
                    user_id=user.id if user and user.is_authenticated else None,
                    username=user.username if user and user.is_authenticated else None,
                    model_name=model_class.__name__,
                    message=f"Erreur lors de {operation}: {str(e)}",
                    details={"operation": operation, "error": str(e)},
                )

                audit_logger.log_event(event)

                raise

        return wrapper

    return decorator


def get_client_ip(request) -> Optional[str]:
    """
    Récupère l'adresse IP du client.

    Args:
        request: Requête HTTP

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
    Génère un hash pour une opération GraphQL.

    Args:
        operation: Opération GraphQL

    Returns:
        Hash de l'opération
    """
    if not operation:
        return ""

    query_string = str(operation)
    return hashlib.sha256(query_string.encode()).hexdigest()[:16]


# Instance globale du gestionnaire d'audit
audit_logger = AuditLogger()
