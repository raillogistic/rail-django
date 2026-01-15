"""
Configuration de sécurité pour Django GraphQL Auto-Generation.

Ce module fournit des configurations et des utilitaires pour :
- Configuration des middlewares de sécurité
- Paramètres d'audit et de logging
- Configuration MFA
- Paramètres de limitation de débit
"""

from typing import Any, Dict, List

from django.conf import settings


class SecurityConfig:
    """
    Gestionnaire de configuration de sécurité centralisé.
    """

    @staticmethod
    def get_middleware_config() -> dict[str, Any]:
        """
        Retourne la configuration des middlewares de sécurité.

        Returns:
            Configuration des middlewares
        """
        return {
            # Configuration d'authentification
            "jwt_header_prefix": getattr(settings, "JWT_AUTH_HEADER_PREFIX", "Bearer"),
            "jwt_header_name": getattr(
                settings, "JWT_AUTH_HEADER_NAME", "HTTP_AUTHORIZATION"
            ),
            "jwt_user_cache_timeout": getattr(settings, "JWT_USER_CACHE_TIMEOUT", 300),
            # Configuration d'audit
            "enable_audit_logging": getattr(
                settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True
            ),
            "audit_store_in_database": getattr(
                settings, "AUDIT_STORE_IN_DATABASE", True
            ),
            "audit_store_in_file": getattr(settings, "AUDIT_STORE_IN_FILE", True),
            "audit_webhook_url": getattr(settings, "AUDIT_WEBHOOK_URL", None),
            "audit_retention_days": getattr(settings, "AUDIT_RETENTION_DAYS", 90),
            # Configuration de limitation de débit
            "enable_rate_limiting": getattr(
                settings, "GRAPHQL_ENABLE_AUTH_RATE_LIMITING", True
            ),
            "login_attempts_limit": getattr(settings, "AUTH_LOGIN_ATTEMPTS_LIMIT", 5),
            "login_attempts_window": getattr(
                settings, "AUTH_LOGIN_ATTEMPTS_WINDOW", 900
            ),
            "graphql_requests_limit": getattr(settings, "GRAPHQL_REQUESTS_LIMIT", 100),
            "graphql_requests_window": getattr(
                settings, "GRAPHQL_REQUESTS_WINDOW", 3600
            ),
            # Endpoints GraphQL
            "graphql_endpoints": getattr(
                settings, "GRAPHQL_ENDPOINTS", ["/graphql/", "/graphql"]
            ),
        }

    @staticmethod
    def get_audit_config() -> dict[str, Any]:
        """
        Retourne la configuration d'audit.

        Returns:
            Configuration d'audit
        """
        return {
            "enabled": getattr(settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True),
            "store_in_database": getattr(settings, "AUDIT_STORE_IN_DATABASE", True),
            "store_in_file": getattr(settings, "AUDIT_STORE_IN_FILE", True),
            "webhook_url": getattr(settings, "AUDIT_WEBHOOK_URL", None),
            "retention_days": getattr(settings, "AUDIT_RETENTION_DAYS", 90),
            "alert_thresholds": getattr(
                settings,
                "AUDIT_ALERT_THRESHOLDS",
                {
                    "failed_logins_per_ip": 10,
                    "failed_logins_per_user": 5,
                    "suspicious_activity_window": 300,
                },
            ),
        }

    @staticmethod
    def get_mfa_config() -> dict[str, Any]:
        """
        Retourne la configuration MFA.

        Returns:
            Configuration MFA
        """
        return {
            "enabled": getattr(settings, "MFA_ENABLED", False),
            "issuer_name": getattr(settings, "MFA_ISSUER_NAME", "Django GraphQL App"),
            "totp_validity_window": getattr(settings, "MFA_TOTP_VALIDITY_WINDOW", 1),
            "backup_codes_count": getattr(settings, "MFA_BACKUP_CODES_COUNT", 10),
            "trusted_device_duration": getattr(
                settings, "MFA_TRUSTED_DEVICE_DURATION", 30
            ),
            "sms_token_length": getattr(settings, "MFA_SMS_TOKEN_LENGTH", 6),
            "sms_token_validity": getattr(settings, "MFA_SMS_TOKEN_VALIDITY", 300),
            "sms_provider": getattr(settings, "MFA_SMS_PROVIDER", None),
            # Configuration Twilio
            "twilio_account_sid": getattr(settings, "TWILIO_ACCOUNT_SID", ""),
            "twilio_auth_token": getattr(settings, "TWILIO_AUTH_TOKEN", ""),
            "twilio_from_number": getattr(settings, "TWILIO_FROM_NUMBER", ""),
        }

    @staticmethod
    def get_security_headers() -> dict[str, str]:
        """
        Retourne les headers de sécurité recommandés.

        Returns:
            Headers de sécurité
        """
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }

    @staticmethod
    def validate_security_settings() -> list[str]:
        """
        Valide les paramètres de sécurité et retourne les avertissements.

        Returns:
            Liste des avertissements de sécurité
        """
        warnings = []

        # Vérifier la configuration JWT
        if not hasattr(settings, "SECRET_KEY") or len(settings.SECRET_KEY) < 32:
            warnings.append("SECRET_KEY trop courte ou manquante")

        # Vérifier la configuration d'audit
        if getattr(settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True):
            if not getattr(settings, "AUDIT_STORE_IN_DATABASE", True) and not getattr(
                settings, "AUDIT_STORE_IN_FILE", True
            ):
                warnings.append("Aucun stockage d'audit configuré")

        # Vérifier la configuration MFA
        if getattr(settings, "MFA_ENABLED", False):
            sms_provider = getattr(settings, "MFA_SMS_PROVIDER", None)
            if sms_provider == "twilio":
                if not getattr(settings, "TWILIO_ACCOUNT_SID", ""):
                    warnings.append("TWILIO_ACCOUNT_SID manquant pour MFA SMS")
                if not getattr(settings, "TWILIO_AUTH_TOKEN", ""):
                    warnings.append("TWILIO_AUTH_TOKEN manquant pour MFA SMS")

        # Vérifier la configuration de limitation de débit
        if getattr(settings, "GRAPHQL_ENABLE_AUTH_RATE_LIMITING", True):
            if not hasattr(settings, "CACHES") or "default" not in settings.CACHES:
                warnings.append(
                    "Configuration de cache manquante pour la limitation de débit"
                )

        return warnings

    @staticmethod
    def get_recommended_django_settings() -> dict[str, Any]:
        """
        Retourne les paramètres Django recommandés pour la sécurité.

        Returns:
            Paramètres Django recommandés
        """
        return {
            # Sécurité générale
            "DEBUG": False,
            "SECURE_BROWSER_XSS_FILTER": True,
            "SECURE_CONTENT_TYPE_NOSNIFF": True,
            "SECURE_HSTS_SECONDS": 31536000,
            "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
            "SECURE_HSTS_PRELOAD": True,
            "X_FRAME_OPTIONS": "DENY",
            # HTTPS
            "SECURE_SSL_REDIRECT": True,
            "SESSION_COOKIE_SECURE": True,
            "CSRF_COOKIE_SECURE": True,
            # Sessions
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Strict",
            "SESSION_EXPIRE_AT_BROWSER_CLOSE": True,
            # CSRF
            "CSRF_COOKIE_HTTPONLY": True,
            "CSRF_COOKIE_SAMESITE": "Strict",
            # Logging
            "LOGGING": {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "verbose": {
                        "format": "[{levelname}] {asctime} {name} {process:d} {thread:d} {message}",
                        "style": "{",
                    },
                    "audit": {
                        "format": "[AUDIT] {asctime} {message}",
                        "style": "{",
                    },
                },
                "handlers": {
                    "security_file": {
                        "level": "INFO",
                        "class": "logging.handlers.RotatingFileHandler",
                        "filename": "logs/security.log",
                        "maxBytes": 1024 * 1024 * 10,  # 10MB
                        "backupCount": 5,
                        "formatter": "verbose",
                    },
                    "audit_file": {
                        "level": "INFO",
                        "class": "logging.handlers.RotatingFileHandler",
                        "filename": "logs/audit.log",
                        "maxBytes": 1024 * 1024 * 10,  # 10MB
                        "backupCount": 10,
                        "formatter": "audit",
                    },
                },
                "loggers": {
                    "rail_django.middleware": {
                        "handlers": ["security_file"],
                        "level": "INFO",
                        "propagate": True,
                    },
                    "audit": {
                        "handlers": ["audit_file"],
                        "level": "INFO",
                        "propagate": False,
                    },
                },
            },
        }


def setup_security_middleware() -> list[str]:
    """
    Retourne la liste des middlewares de sécurité à ajouter à MIDDLEWARE.

    Returns:
        Liste des middlewares de sécurité
    """
    security_middleware = []

    # Middleware d'authentification (doit être avant les middlewares GraphQL)
    security_middleware.append("rail_django.middleware.GraphQLAuthenticationMiddleware")

    # Middleware de limitation de débit
    if getattr(settings, "GRAPHQL_ENABLE_AUTH_RATE_LIMITING", True):
        security_middleware.append("rail_django.middleware.GraphQLRateLimitMiddleware")

    return security_middleware


def get_security_status() -> dict[str, Any]:
    """
    Retourne le statut de sécurité actuel.

    Returns:
        Statut de sécurité
    """
    config = SecurityConfig()

    return {
        "middleware_configured": True,
        "audit_enabled": config.get_audit_config()["enabled"],
        "mfa_enabled": config.get_mfa_config()["enabled"],
        "rate_limiting_enabled": config.get_middleware_config()["enable_rate_limiting"],
        "security_warnings": config.validate_security_settings(),
        "recommended_settings": config.get_recommended_django_settings(),
    }
