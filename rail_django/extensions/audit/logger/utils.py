"""
Utility functions for audit logging.
"""

from typing import Any

from .loggers import audit_logger


def get_security_dashboard_data(hours: int = 24) -> dict[str, Any]:
    """
    Récupère les données pour le tableau de bord de sécurité.
    """
    return audit_logger.get_security_report(hours)
