"""
AuditLogger implementation and utility functions.
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.http import HttpRequest
from django.utils import timezone as django_timezone
from django.utils.module_loading import import_string

from .types import AuditEvent, AuditEventType, AuditSeverity
from .models import get_audit_event_model

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Gestionnaire principal pour l'audit des événements d'authentification.
    """

    def __init__(self, debug: bool = None):
        """
        Initialise le logger d'audit.
        """
        self.enabled = getattr(settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True)
        self.store_in_db = getattr(settings, "AUDIT_STORE_IN_DATABASE", True)
        self.store_in_file = getattr(settings, "AUDIT_STORE_IN_FILE", True)
        self.webhook_url = getattr(settings, "AUDIT_WEBHOOK_URL", None)
        self.retention_days = getattr(settings, "AUDIT_RETENTION_DAYS", 90)
        self.retention_interval_seconds = int(
            getattr(settings, "AUDIT_RETENTION_RUN_INTERVAL", 3600)
        )
        self._last_retention_run = 0.0
        self.redaction_mask = getattr(
            settings, "AUDIT_REDACTION_MASK", "***REDACTED***"
        )
        self.redact_error_messages = bool(
            getattr(settings, "AUDIT_REDACT_ERROR_MESSAGES", True)
        )
        self.redaction_fields = self._load_redaction_fields()
        self._retention_hook = self._resolve_retention_hook()

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
        self._failed_login_ip_state: dict[str, list[float]] = {}
        self._failed_login_user_state: dict[str, list[float]] = {}

    def _load_redaction_fields(self) -> list[str]:
        default_fields = [
            "password", "token", "secret", "key", "credential",
            "authorization", "email", "phone", "ssn",
        ]
        fields = getattr(settings, "AUDIT_REDACTION_FIELDS", None)
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split(",") if f.strip()]
        if isinstance(fields, (list, tuple, set)):
            return [str(f).lower() for f in fields if f]
        return default_fields

    def _resolve_retention_hook(self):
        hook = getattr(settings, "AUDIT_RETENTION_HOOK", None)
        if not hook:
            return None
        if callable(hook):
            return hook
        if isinstance(hook, str):
            try:
                return import_string(hook)
            except Exception as exc:
                logger.warning("Failed to import audit retention hook: %s", exc)
                return None
        return None

    def log_event(self, event: AuditEvent) -> None:
        """
        Enregistre un événement d'audit.
        """
        if not self.enabled:
            return

        try:
            event = self._redact_event(event)
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

            self._apply_retention_policy()
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de l'événement d'audit: {e}")

    def _redact_event(self, event: AuditEvent) -> AuditEvent:
        if event.additional_data:
            event.additional_data = self._redact_payload(event.additional_data)
        if event.error_message and self.redact_error_messages:
            if self._contains_sensitive_terms(event.error_message):
                event.error_message = self.redaction_mask
        return event

    def _contains_sensitive_terms(self, value: str) -> bool:
        lowered = value.lower()
        return any(term in lowered for term in self.redaction_fields)

    def _redact_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            redacted: dict[str, Any] = {}
            for key, value in payload.items():
                if str(key).lower() in self.redaction_fields:
                    redacted[key] = self.redaction_mask
                else:
                    redacted[key] = self._redact_payload(value)
            return redacted
        if isinstance(payload, list):
            return [self._redact_payload(item) for item in payload]
        return payload

    def _apply_retention_policy(self) -> None:
        if not self.store_in_db or not self.retention_days:
            return
        now = time.time()
        if self.retention_interval_seconds:
            if now - self._last_retention_run < self.retention_interval_seconds:
                return
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        try:
            get_audit_event_model().objects.filter(timestamp__lt=cutoff).delete()
        except Exception as exc:
            logger.warning("Failed to apply audit retention: %s", exc)
        if self._retention_hook:
            try:
                self._retention_hook(cutoff=cutoff, logger=self)
            except Exception as exc:
                logger.warning("Retention hook failed: %s", exc)
        self._last_retention_run = now

    def log_login_attempt(
        self,
        request: HttpRequest,
        user: Optional["AbstractUser"],
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Enregistre une tentative de connexion.
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
        details: dict[str, Any],
        user: Optional["AbstractUser"] = None,
    ) -> None:
        """
        Enregistre une activité suspecte.
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

    def get_security_report(self, hours: int = 24) -> dict[str, Any]:
        """
        Génère un rapport de sécurité pour les dernières heures.
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
        """
        audit_logger_file = logging.getLogger("audit")
        audit_logger_file.info(json.dumps(event.to_dict(), ensure_ascii=False))

    def _log_to_database(self, event: AuditEvent) -> None:
        """
        Enregistre l'événement en base de données.
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
        """
        alert_message = message or f"Alerte de sécurité: {event.event_type.value}"

        # Logger l'alerte
        logger.critical(f"ALERTE SÉCURITÉ: {alert_message} - {event.to_dict()}")

        # Envoyer une notification (email, Slack, etc.)
        self._send_security_notification(alert_message, event)

    def _send_security_notification(self, message: str, event: AuditEvent) -> None:
        """
        Envoie une notification de sécurité.
        """
        pass

    def _get_client_ip(self, request: HttpRequest) -> str:
        """
        Récupère l'adresse IP du client.
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


def log_audit_event(
    request: Optional[HttpRequest],
    event_type: AuditEventType,
    *,
    severity: Optional[AuditSeverity] = None,
    user: Optional["AbstractUser"] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    additional_data: Optional[dict[str, Any]] = None,
    request_path: Optional[str] = None,
    request_method: Optional[str] = None,
) -> None:
    """Log a generic audit event with standard request metadata."""
    if not audit_logger.enabled:
        return

    resolved_event_type = event_type
    if isinstance(event_type, str):
        try:
            resolved_event_type = AuditEventType(event_type)
        except ValueError:
            resolved_event_type = AuditEventType.DATA_ACCESS

    if severity is None:
        if resolved_event_type in (
            AuditEventType.CREATE,
            AuditEventType.UPDATE,
            AuditEventType.DELETE,
        ):
            severity = AuditSeverity.MEDIUM
        else:
            severity = AuditSeverity.LOW

    if user is None and request is not None:
        user = getattr(request, "user", None)

    user_id = None
    username = None
    if user and getattr(user, "is_authenticated", False):
        user_id = getattr(user, "id", None)
        if hasattr(user, "get_username"):
            username = user.get_username()
        else:
            username = getattr(user, "username", None)

    client_ip = audit_logger._get_client_ip(request) if request is not None else "Unknown"
    user_agent = (
        request.META.get("HTTP_USER_AGENT", "Unknown") if request is not None else "Unknown"
    )
    resolved_path = request_path or (request.path if request is not None else "")
    resolved_method = request_method or (request.method if request is not None else "SYSTEM")
    session_id = (
        request.session.session_key
        if request is not None and hasattr(request, "session")
        else None
    )

    event = AuditEvent(
        event_type=resolved_event_type,
        severity=severity,
        user_id=user_id,
        username=username,
        client_ip=client_ip,
        user_agent=user_agent,
        timestamp=datetime.now(timezone.utc),
        request_path=resolved_path,
        request_method=resolved_method,
        additional_data=additional_data,
        session_id=session_id,
        success=success,
        error_message=error_message,
    )

    audit_logger.log_event(event)


def log_authentication_event(
    request: HttpRequest,
    user: Optional["AbstractUser"],
    event_type: str,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """
    Fonction utilitaire pour enregistrer un événement d'authentification.
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


def get_security_dashboard_data(hours: int = 24) -> dict[str, Any]:
    """
    Récupère les données pour le tableau de bord de sécurité.
    """
    return audit_logger.get_security_report(hours)
