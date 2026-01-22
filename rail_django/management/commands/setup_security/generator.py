"""
Security settings generator.
"""

from ....security_config import SecurityConfig


def generate_settings_content(enable_mfa: bool = False) -> str:
    """
    Génère le contenu du fichier de paramètres de sécurité.

    Args:
        enable_mfa: Whether MFA is enabled.

    Returns:
        Contenu du fichier de paramètres
    """
    config = SecurityConfig()
    # Note: We aren't using config.get_recommended_django_settings() directly in the output string
    # because the original code constructs a Python file string.
    # We maintain the original behavior of generating a complete python file.

    content = '''"""
Paramètres de sécurité recommandés pour Django GraphQL Auto-Generation.

Ce fichier contient les paramètres de sécurité recommandés.
Importez ce fichier dans votre settings.py principal :

    from .security_settings import *

Ou ajoutez les paramètres individuellement selon vos besoins.
"""

import os
from pathlib import Path

# Répertoire de base du projet
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# PARAMÈTRES DE SÉCURITÉ DJANGO
# =============================================================================

# Sécurité générale
DEBUG = False
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = 'DENY'

# HTTPS (à activer en production)
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True

# Sessions
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 3600  # 1 heure

# CSRF
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'

# =============================================================================
# MIDDLEWARES DE SÉCURITÉ
# =============================================================================

# Ajouter ces middlewares à votre MIDDLEWARE existant
SECURITY_MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'rail_django.middleware.GraphQLAuthenticationMiddleware',
    'rail_django.middleware.GraphQLRateLimitMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# =============================================================================
# CONFIGURATION GRAPHQL SÉCURISÉE
# =============================================================================

# Désactiver les mutations de sécurité en production
disable_security_mutations = False

# Endpoints GraphQL
GRAPHQL_ENDPOINTS = ['/graphql/', '/graphql']

# Configuration JWT
JWT_AUTH_HEADER_PREFIX = 'Bearer'
JWT_AUTH_HEADER_NAME = 'HTTP_AUTHORIZATION'
JWT_USER_CACHE_TIMEOUT = 300  # 5 minutes

# =============================================================================
# AUDIT LOGGING
# =============================================================================

GRAPHQL_ENABLE_AUDIT_LOGGING = True
AUDIT_STORE_IN_DATABASE = True
AUDIT_STORE_IN_FILE = True
AUDIT_RETENTION_DAYS = 90
AUDIT_WEBHOOK_URL = None  # URL pour envoyer les événements d'audit

# Seuils d'alerte pour l'audit
AUDIT_ALERT_THRESHOLDS = {
    'failed_logins_per_ip': 10,
    'failed_logins_per_user': 5,
    'suspicious_activity_window': 300,  # 5 minutes
}

# =============================================================================
# LIMITATION DE DÉBIT
# =============================================================================

GRAPHQL_ENABLE_AUTH_RATE_LIMITING = True
AUTH_LOGIN_ATTEMPTS_LIMIT = 5
AUTH_LOGIN_ATTEMPTS_WINDOW = 900  # 15 minutes
GRAPHQL_REQUESTS_LIMIT = 100
GRAPHQL_REQUESTS_WINDOW = 3600  # 1 heure

# =============================================================================
# AUTHENTIFICATION MULTI-FACTEURS (MFA)
# =============================================================================

'''

    if enable_mfa:
        content += """
MFA_ENABLED = True
MFA_ISSUER_NAME = 'Django GraphQL App'
MFA_TOTP_VALIDITY_WINDOW = 1
MFA_BACKUP_CODES_COUNT = 10
MFA_TRUSTED_DEVICE_DURATION = 30  # jours
MFA_SMS_TOKEN_LENGTH = 6
MFA_SMS_TOKEN_VALIDITY = 300  # 5 minutes

# Configuration SMS (Twilio)
MFA_SMS_PROVIDER = 'twilio'
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER', '')
"""
    else:
        content += """
MFA_ENABLED = False
"""

    content += """

# =============================================================================
# CONFIGURATION DE CACHE
# =============================================================================

# Note: Les fonctionnalités GraphQL internes n'exigent pas de cache externe.
# Utilisez LocMemCache pendant le développement/test si votre projet a besoin
# d'un cache pour d'autres composants. Les vérifications de santé utilisent
# des caches en mémoire par processus avec TTL.

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'KEY_PREFIX': 'graphql_security',
        'TIMEOUT': 3600,
    }
}

# =============================================================================
# LOGGING SÉCURISÉ
# =============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'audit': {
            'format': '[AUDIT] {asctime} {message}',
            'style': '{',
        },
        'security': {
            'format': '[SECURITY] {asctime} {name} {levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'security_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'maxBytes': 1024*1024*10,  # 10MB
            'backupCount': 5,
            'formatter': 'security',
        },
        'audit_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'audit.log',
            'maxBytes': 1024*1024*10,  # 10MB
            'backupCount': 10,
            'formatter': 'audit',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'rail_django.middleware': {
            'handlers': ['security_file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'audit': {
            'handlers': ['audit_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['security_file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# =============================================================================
# VARIABLES D'ENVIRONNEMENT RECOMMANDÉES
# =============================================================================

# Ajoutez ces variables à votre fichier .env :
# SECRET_KEY=your-very-long-and-random-secret-key-here
# DEBUG=False
# TWILIO_ACCOUNT_SID=your-twilio-account-sid
# TWILIO_AUTH_TOKEN=your-twilio-auth-token
# TWILIO_FROM_NUMBER=your-twilio-phone-number
# AUDIT_WEBHOOK_URL=https://your-audit-webhook-url.com/webhook
"""

    return content
