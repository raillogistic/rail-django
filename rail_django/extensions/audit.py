"""
Système d'audit pour les événements d'authentification Django GraphQL.

Ce module fournit un système complet d'audit pour :
- Les tentatives de connexion (réussies et échouées)
- Les actions d'authentification
- Les événements de sécurité
- L'analyse des patterns d'attaque
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from doctest import debug
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import time
import graphene
from graphql import GraphQLError

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.http import HttpRequest
from django.utils import timezone as django_timezone

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types d'événements d'audit."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_INVALID = "token_invalid"
    REGISTRATION = "registration"
    PASSWORD_CHANGE = "password_change"
    ACCOUNT_LOCKED = "account_locked"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMITED = "rate_limited"
    MFA_SUCCESS = "mfa_success"
    MFA_FAILURE = "mfa_failure"
    UI_ACTION = "ui_action"


class AuditSeverity(Enum):
    """Niveaux de gravité des événements d'audit."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """
    Représente un événement d'audit.

    Attributes:
        event_type: Type d'événement
        severity: Niveau de gravité
        user_id: ID de l'utilisateur concerné
        username: Nom d'utilisateur
        client_ip: Adresse IP du client
        user_agent: User agent du navigateur
        timestamp: Horodatage de l'événement
        request_path: Chemin de la requête
        request_method: Méthode HTTP
        additional_data: Données supplémentaires
        session_id: ID de session
        success: Indique si l'action a réussi
        error_message: Message d'erreur le cas échéant
    """

    event_type: AuditEventType
    severity: AuditSeverity
    client_ip: str
    user_agent: str
    timestamp: datetime
    request_path: str
    request_method: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'événement en dictionnaire."""
        data = asdict(self)
        data["event_type"] = self.event_type.value
        data["severity"] = self.severity.value
        data["timestamp"] = self.timestamp.isoformat()
        return data


# Remove the model definition - it's now in apps.core.models
# Use lazy import to defer model access until Django apps are ready
def get_audit_event_model():
    """Lazy import for AuditEventModel to avoid AppRegistryNotReady errors."""
    from apps.core.models import AuditEventModel

    return AuditEventModel


class AuditLogger:
    """
    Gestionnaire principal pour l'audit des événements d'authentification.
    """

    def __init__(self, debug: bool = None):
        """
        Initialise le logger d'audit.

        Args:
            debug: Mode debug - si True, les événements sont enregistrés mais les alertes sont désactivées
        """
        self.enabled = getattr(settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True)
        self.store_in_db = getattr(settings, "AUDIT_STORE_IN_DATABASE", True)
        self.store_in_file = getattr(settings, "AUDIT_STORE_IN_FILE", True)
        self.webhook_url = getattr(settings, "AUDIT_WEBHOOK_URL", None)
        self.retention_days = getattr(settings, "AUDIT_RETENTION_DAYS", 90)

        # Mode debug - si None, utilise la configuration Django DEBUG
        if debug is None:
            self.debug = getattr(settings, "DEBUG", False)
        else:
            self.debug = debug

        # Configuration des alertes
        self.alert_thresholds = getattr(
            settings,
            "AUDIT_ALERT_THRESHOLDS",
            {
                "failed_logins_per_ip": 10,
                "failed_logins_per_user": 5,
                "suspicious_activity_window": 300,  # 5 minutes
            },
        )

        # In-memory counters for failed login tracking (per-process)
        # Structure: {key: [count, window_start_ts]}
        self._failed_login_ip_state: Dict[str, List[float]] = {}
        self._failed_login_user_state: Dict[str, List[float]] = {}

    def log_event(self, event: AuditEvent) -> None:
        """
        Enregistre un événement d'audit.

        Args:
            event: Événement d'audit à enregistrer
        """
        if not self.enabled:
            return

        try:
            # Enregistrer dans les logs
            if self.store_in_file:
                self._log_to_file(event)

            # Enregistrer en base de données
            if self.store_in_db:
                self._log_to_database(event)

            # Envoyer vers un webhook externe
            if self.webhook_url:
                self._send_to_webhook(event)

            # Vérifier les seuils d'alerte
            self._check_alert_thresholds(event)

        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de l'événement d'audit: {e}")

    def log_login_attempt(
        self,
        request: HttpRequest,
        user: Optional["AbstractUser"],
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Enregistre une tentative de connexion.

        Args:
            request: Requête HTTP
            user: Utilisateur concerné
            success: Indique si la connexion a réussi
            error_message: Message d'erreur le cas échéant
        """
        event_type = (
            AuditEventType.LOGIN_SUCCESS if success else AuditEventType.LOGIN_FAILURE
        )
        severity = AuditSeverity.LOW if success else AuditSeverity.MEDIUM

        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            user_id=user.id if user else None,
            username=user.username if user else None,
            client_ip=self._get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "Unknown"),
            timestamp=datetime.now(timezone.utc),
            request_path=request.path,
            request_method=request.method,
            success=success,
            error_message=error_message,
            session_id=request.session.session_key
            if hasattr(request, "session")
            else None,
        )

        self.log_event(event)

    def log_logout(self, request: HttpRequest, user: "AbstractUser") -> None:
        """
        Enregistre une déconnexion.

        Args:
            request: Requête HTTP
            user: Utilisateur qui se déconnecte
        """
        event = AuditEvent(
            event_type=AuditEventType.LOGOUT,
            severity=AuditSeverity.LOW,
            user_id=user.id,
            username=user.username,
            client_ip=self._get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "Unknown"),
            timestamp=datetime.now(timezone.utc),
            request_path=request.path,
            request_method=request.method,
            session_id=request.session.session_key
            if hasattr(request, "session")
            else None,
        )

        self.log_event(event)

    def log_token_event(
        self,
        request: HttpRequest,
        user: Optional["AbstractUser"],
        event_type: AuditEventType,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Enregistre un événement lié aux tokens.

        Args:
            request: Requête HTTP
            user: Utilisateur concerné
            event_type: Type d'événement token
            success: Indique si l'opération a réussi
            error_message: Message d'erreur le cas échéant
        """
        severity = AuditSeverity.LOW if success else AuditSeverity.MEDIUM

        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            user_id=user.id if user else None,
            username=user.username if user else None,
            client_ip=self._get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "Unknown"),
            timestamp=datetime.now(timezone.utc),
            request_path=request.path,
            request_method=request.method,
            success=success,
            error_message=error_message,
        )

        self.log_event(event)

    def log_suspicious_activity(
        self,
        request: HttpRequest,
        activity_type: str,
        details: Dict[str, Any],
        user: Optional["AbstractUser"] = None,
    ) -> None:
        """
        Enregistre une activité suspecte.

        Args:
            request: Requête HTTP
            activity_type: Type d'activité suspecte
            details: Détails de l'activité
            user: Utilisateur concerné le cas échéant
        """
        event = AuditEvent(
            event_type=AuditEventType.SUSPICIOUS_ACTIVITY,
            severity=AuditSeverity.HIGH,
            user_id=user.id if user else None,
            username=user.username if user else None,
            client_ip=self._get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "Unknown"),
            timestamp=datetime.now(timezone.utc),
            request_path=request.path,
            request_method=request.method,
            additional_data={"activity_type": activity_type, "details": details},
        )

        self.log_event(event)

    def log_rate_limit_exceeded(self, request: HttpRequest, limit_type: str) -> None:
        """
        Enregistre un dépassement de limite de débit.

        Args:
            request: Requête HTTP
            limit_type: Type de limite dépassée
        """
        event = AuditEvent(
            event_type=AuditEventType.RATE_LIMITED,
            severity=AuditSeverity.MEDIUM,
            client_ip=self._get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "Unknown"),
            timestamp=datetime.now(timezone.utc),
            request_path=request.path,
            request_method=request.method,
            success=False,
            additional_data={"limit_type": limit_type},
        )

        self.log_event(event)

    def get_security_report(self, hours: int = 24) -> Dict[str, Any]:
        """
        Génère un rapport de sécurité pour les dernières heures.

        Args:
            hours: Nombre d'heures à analyser

        Returns:
            Rapport de sécurité
        """
        if not self.store_in_db:
            return {"error": "Database storage not enabled"}

        try:
            from django.utils import timezone

            since = timezone.now() - timezone.timedelta(hours=hours)

            events = get_audit_event_model().objects.filter(timestamp__gte=since)

            report = {
                "period_hours": hours,
                "total_events": events.count(),
                "failed_logins": events.filter(
                    event_type=AuditEventType.LOGIN_FAILURE.value
                ).count(),
                "successful_logins": events.filter(
                    event_type=AuditEventType.LOGIN_SUCCESS.value
                ).count(),
                "suspicious_activities": events.filter(
                    event_type=AuditEventType.SUSPICIOUS_ACTIVITY.value
                ).count(),
                "rate_limited_requests": events.filter(
                    event_type=AuditEventType.RATE_LIMITED.value
                ).count(),
                "top_failed_ips": list(
                    events.filter(event_type=AuditEventType.LOGIN_FAILURE.value)
                    .values("client_ip")
                    .annotate(count=models.Count("client_ip"))
                    .order_by("-count")[:10]
                ),
                "top_targeted_users": list(
                    events.filter(
                        event_type=AuditEventType.LOGIN_FAILURE.value,
                        username__isnull=False,
                    )
                    .values("username")
                    .annotate(count=models.Count("username"))
                    .order_by("-count")[:10]
                ),
            }

            return report

        except Exception as e:
            logger.error(f"Erreur lors de la génération du rapport de sécurité: {e}")
            return {"error": str(e)}

    def _log_to_file(self, event: AuditEvent) -> None:
        """
        Enregistre l'événement dans un fichier de log.

        Args:
            event: Événement à enregistrer
        """
        audit_logger = logging.getLogger("audit")
        audit_logger.info(json.dumps(event.to_dict(), ensure_ascii=False))

    def _log_to_database(self, event: AuditEvent) -> None:
        """
        Enregistre l'événement en base de données.

        Args:
            event: Événement à enregistrer
        """
        try:
            get_audit_event_model().objects.create(
                event_type=event.event_type.value,
                severity=event.severity.value,
                user_id=event.user_id,
                username=event.username,
                client_ip=event.client_ip,
                user_agent=event.user_agent,
                timestamp=event.timestamp,
                request_path=event.request_path,
                request_method=event.request_method,
                additional_data=event.additional_data,
                session_id=event.session_id,
                success=event.success,
                error_message=event.error_message,
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement en base de données: {e}")

    def _send_to_webhook(self, event: AuditEvent) -> None:
        """
        Envoie l'événement vers un webhook externe.

        Args:
            event: Événement à envoyer
        """
        try:
            import requests

            response = requests.post(
                self.webhook_url,
                json=event.to_dict(),
                timeout=5,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi vers le webhook: {e}")

    def _check_alert_thresholds(self, event: AuditEvent) -> None:
        """
        Vérifie les seuils d'alerte et déclenche des alertes si nécessaire.
        En mode debug, les événements sont traités mais les alertes sont supprimées.

        Args:
            event: Événement à vérifier
        """
        try:
            # Vérifier les échecs de connexion par IP
            if event.event_type == AuditEventType.LOGIN_FAILURE:
                self._check_failed_logins_by_ip(event)

                # Vérifier les échecs de connexion par utilisateur
                if event.username:
                    self._check_failed_logins_by_user(event)

            # Vérifier les activités suspectes (seulement si pas en mode debug)
            if event.severity == AuditSeverity.HIGH:
                if self.debug:
                    logger.debug(
                        f"Debug mode: High severity event detected but alert suppressed - {event.event_type}"
                    )
                else:
                    self._trigger_security_alert(event)

        except Exception as e:
            logger.error(f"Erreur lors de la vérification des seuils d'alerte: {e}")

    def _check_failed_logins_by_ip(self, event: AuditEvent) -> None:
        """
        Vérifie les tentatives de connexion échouées par IP.
        En mode debug, enregistre l'événement mais ne déclenche pas d'alerte.

        Args:
            event: L'événement d'audit à vérifier
        """
        key = str(event.client_ip)
        now = time.time()
        window = float(self.alert_thresholds.get("suspicious_activity_window", 300))
        state = self._failed_login_ip_state.get(key, [0.0, now])
        count = int(state[0])
        window_start = float(state[1])

        # Reset window if expired
        if now - window_start >= window:
            count = 0
            window_start = now

        # Increment counter
        count += 1
        self._failed_login_ip_state[key] = [float(count), window_start]

        # En mode debug, on enregistre mais on ne déclenche pas d'alerte
        if self.debug:
            logger.debug(
                f"Debug mode: Failed login attempt #{count} from IP {event.client_ip} - Alert suppressed"
            )
            return

        threshold = int(self.alert_thresholds.get("failed_logins_per_ip", 10))
        if count >= threshold and not self.debug:
            self._trigger_security_alert(
                event,
                f"Trop de tentatives de connexion échouées depuis l'IP {event.client_ip}",
            )

    def _check_failed_logins_by_user(self, event: AuditEvent) -> None:
        """
        Vérifie les tentatives de connexion échouées par utilisateur.
        En mode debug, enregistre l'événement mais ne déclenche pas d'alerte.

        Args:
            event: L'événement d'audit à vérifier
        """
        if not event.username:
            return

        key = str(event.username)
        now = time.time()
        window = float(self.alert_thresholds.get("suspicious_activity_window", 300))
        state = self._failed_login_user_state.get(key, [0.0, now])
        count = int(state[0])
        window_start = float(state[1])

        # Reset window if expired
        if now - window_start >= window:
            count = 0
            window_start = now

        # Increment counter
        count += 1
        self._failed_login_user_state[key] = [float(count), window_start]

        # En mode debug, on enregistre mais on ne déclenche pas d'alerte
        if self.debug:
            logger.debug(
                f"Debug mode: Failed login attempt #{count} for user {event.username} - Alert suppressed"
            )
            return

        threshold = int(self.alert_thresholds.get("failed_logins_per_user", 5))
        if count >= threshold:
            self._trigger_security_alert(
                event,
                f"Utilisateur {event.username} a échoué {count} tentatives de connexion",
            )

    def _trigger_security_alert(
        self, event: AuditEvent, message: Optional[str] = None
    ) -> None:
        """
        Déclenche une alerte de sécurité.

        Args:
            event: Événement déclencheur
            message: Message d'alerte personnalisé
        """
        alert_message = message or f"Alerte de sécurité: {event.event_type.value}"

        # Logger l'alerte
        logger.critical(f"ALERTE SÉCURITÉ: {alert_message} - {event.to_dict()}")

        # Envoyer une notification (email, Slack, etc.)
        self._send_security_notification(alert_message, event)

    def _send_security_notification(self, message: str, event: AuditEvent) -> None:
        """
        Envoie une notification de sécurité.

        Args:
            message: Message d'alerte
            event: Événement déclencheur
        """
        # Cette méthode peut être étendue pour envoyer des notifications via :
        # - Email
        # - Slack
        # - SMS
        # - Système de monitoring (PagerDuty, etc.)
        pass

    def _get_client_ip(self, request: HttpRequest) -> str:
        """
        Récupère l'adresse IP du client.

        Args:
            request: Requête HTTP

        Returns:
            Adresse IP du client
        """
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.META.get("HTTP_X_REAL_IP")
        if real_ip:
            return real_ip

        return request.META.get("REMOTE_ADDR", "Unknown")


# Instance globale du logger d'audit
audit_logger = AuditLogger()


class FrontendAuditEventInput(graphene.InputObjectType):
    """Input GraphQL pour tracer les actions de l'interface utilisateur."""

    app_name = graphene.String(required=True, description="Nom de l'application ciblée")
    model_name = graphene.String(required=True, description="Nom du modèle ciblé")
    operation = graphene.String(required=True, description="Action métier déclenchée")
    component = graphene.String(
        required=True, description="Composant UI source de l'action"
    )
    description = graphene.String(description="Description libre de l'action")
    severity = graphene.String(
        description="Niveau de gravité (low, medium, high, critical)",
        default_value=AuditSeverity.LOW.value,
    )
    metadata = graphene.JSONString(
        description="Données additionnelles pour aider à la corrélation"
    )
    success = graphene.Boolean(
        description="Indique si l'action a été réalisée avec succès",
        default_value=True,
    )
    source_route = graphene.String(
        description="Route frontend depuis laquelle l'action a été initiée"
    )
    roles = graphene.List(
        graphene.String,
        description="Liste des rôles/permissions détenus côté UI",
    )


class LogFrontendAuditMutation(graphene.Mutation):
    """Mutation GraphQL permettant de journaliser une action utilisateur côté frontend."""

    class Arguments:
        input = graphene.Argument(FrontendAuditEventInput, required=True)

    ok = graphene.Boolean()
    error = graphene.String()

    @staticmethod
    def mutate(root, info, input: dict):
        request = getattr(info, "context", None)
        if request is None:
            raise GraphQLError("Contexte de requête invalide.")
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise GraphQLError(
                "Authentification requise pour journaliser cette action."
            )
        severity_raw = str(input.get("severity") or AuditSeverity.LOW.value).upper()
        severity = AuditSeverity.__members__.get(severity_raw, AuditSeverity.LOW)

        additional_data = {
            "app_name": input.get("app_name"),
            "model_name": input.get("model_name"),
            "operation": input.get("operation"),
            "component": input.get("component"),
            "roles": input.get("roles") or [],
            "metadata": input.get("metadata") or {},
            "description": input.get("description"),
        }

        event = AuditEvent(
            event_type=AuditEventType.UI_ACTION,
            severity=severity,
            user_id=getattr(user, "id", None),
            username=getattr(user, "get_username", lambda: None)(),
            client_ip=audit_logger._get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "Unknown"),
            timestamp=datetime.now(timezone.utc),
            request_path=input.get("source_route") or getattr(request, "path", "/"),
            request_method=getattr(request, "method", "UI"),
            additional_data=additional_data,
            success=bool(input.get("success", True)),
        )
        try:
            audit_logger.log_event(event)
            return LogFrontendAuditMutation(ok=True, error=None)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"Erreur lors de l'enregistrement d'un audit frontend: {exc}")
            return LogFrontendAuditMutation(
                ok=False, error="Impossible d'enregistrer l'audit."
            )


def log_authentication_event(
    request: HttpRequest,
    user: Optional["AbstractUser"],
    event_type: str,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """
    Fonction utilitaire pour enregistrer un événement d'authentification.

    Args:
        request: Requête HTTP
        user: Utilisateur concerné
        event_type: Type d'événement
        success: Indique si l'opération a réussi
        error_message: Message d'erreur le cas échéant
    """
    if event_type == "login":
        audit_logger.log_login_attempt(request, user, success, error_message)
    elif event_type == "logout":
        if user:
            audit_logger.log_logout(request, user)
    elif event_type in ["token_refresh", "token_invalid"]:
        token_event_type = (
            AuditEventType.TOKEN_REFRESH
            if event_type == "token_refresh"
            else AuditEventType.TOKEN_INVALID
        )
        audit_logger.log_token_event(
            request, user, token_event_type, success, error_message
        )


def get_security_dashboard_data(hours: int = 24) -> Dict[str, Any]:
    """
    Récupère les données pour le tableau de bord de sécurité.

    Args:
        hours: Nombre d'heures à analyser

    Returns:
        Données du tableau de bord
    """
    return audit_logger.get_security_report(hours)
