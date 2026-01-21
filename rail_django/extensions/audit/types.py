"""
Audit event types and classes.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


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
    DATA_ACCESS = "data_access"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


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
    additional_data: Optional[dict[str, Any]] = None
    session_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'événement en dictionnaire."""
        data = asdict(self)
        data["event_type"] = self.event_type.value
        data["severity"] = self.severity.value
        data["timestamp"] = self.timestamp.isoformat()
        return data
