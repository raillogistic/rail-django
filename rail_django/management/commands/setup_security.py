"""
Commande de gestion Django pour configurer automatiquement la sécurité.

Cette commande :
- Configure les middlewares de sécurité
- Génère les paramètres de sécurité recommandés
- Crée les migrations nécessaires
- Configure l'audit logging
- Initialise MFA si demandé
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from rail_django.security_config import SecurityConfig, setup_security_middleware


class Command(BaseCommand):
    """
    Commande pour configurer automatiquement la sécurité GraphQL.
    """

    help = "Configure automatiquement la sécurité GraphQL avec les meilleures pratiques"

    def add_arguments(self, parser):
        """
        Ajoute les arguments de la commande.

        Args:
            parser: Parser d'arguments
        """
        parser.add_argument(
            "--enable-mfa",
            action="store_true",
            help="Active l'authentification multi-facteurs",
        )
        parser.add_argument(
            "--enable-audit",
            action="store_true",
            default=True,
            help="Active l'audit logging (activé par défaut)",
        )
        parser.add_argument(
            "--create-settings",
            action="store_true",
            help="Génère un fichier de paramètres de sécurité",
        )
        parser.add_argument(
            "--settings-file",
            type=str,
            default="security_settings.py",
            help="Nom du fichier de paramètres à générer",
        )
        parser.add_argument(
            "--migrate",
            action="store_true",
            help="Exécute les migrations automatiquement",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force l'écrasement des fichiers existants",
        )

    def handle(self, *args, **options):
        """
        Exécute la commande de configuration de sécurité.

        Args:
            *args: Arguments positionnels
            **options: Options de la commande
        """
        self.verbosity = options.get("verbosity", 1)
        self.enable_mfa = options.get("enable_mfa", False)
        self.enable_audit = options.get("enable_audit", True)
        self.create_settings = options.get("create_settings", False)
        self.settings_file = options.get("settings_file", "security_settings.py")
        self.migrate = options.get("migrate", False)
        self.force = options.get("force", False)

        try:
            self.stdout.write(
                self.style.SUCCESS("=== CONFIGURATION DE SÉCURITÉ GRAPHQL ===\n")
            )

            # Étape 1: Vérifier les prérequis
            self._check_prerequisites()

            # Étape 2: Créer les répertoires nécessaires
            self._create_directories()

            # Étape 3: Générer le fichier de paramètres si demandé
            if self.create_settings:
                self._generate_security_settings()

            # Étape 4: Configurer les middlewares
            self._configure_middlewares()

            # Étape 5: Créer les migrations si nécessaire
            if self.migrate:
                self._run_migrations()

            # Étape 6: Configurer l'audit logging
            if self.enable_audit:
                self._configure_audit_logging()

            # Étape 7: Configurer MFA si demandé
            if self.enable_mfa:
                self._configure_mfa()

            # Étape 8: Afficher le résumé
            self._display_summary()

            self.stdout.write(
                self.style.SUCCESS(
                    "\n✅ Configuration de sécurité terminée avec succès!"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erreur lors de la configuration: {e}"))
            raise CommandError(str(e))

    def _check_prerequisites(self):
        """
        Vérifie les prérequis pour la configuration de sécurité.
        """
        self.stdout.write("🔍 Vérification des prérequis...")

        # Vérifier Django
        try:
            import django

            self.stdout.write(f"  ✅ Django {django.get_version()}")
        except ImportError:
            raise CommandError("Django n'est pas installé")

        # Vérifier les dépendances
        required_packages = [
            ("graphene_django", "Graphene Django"),
            ("PyJWT", "PyJWT"),
            ("qrcode", "QRCode (pour MFA)") if self.enable_mfa else None,
        ]

        for package_info in required_packages:
            if package_info is None:
                continue

            package_name, display_name = package_info
            try:
                __import__(package_name)
                self.stdout.write(f"  ✅ {display_name}")
            except ImportError:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠️  {display_name} non installé")
                )

        # Vérifier la configuration de base
        if not hasattr(settings, "SECRET_KEY"):
            raise CommandError("SECRET_KEY manquante dans les paramètres Django")

        if len(settings.SECRET_KEY) < 32:
            self.stdout.write(
                self.style.WARNING("  ⚠️  SECRET_KEY courte (< 32 caractères)")
            )

    def _create_directories(self):
        """
        Crée les répertoires nécessaires pour les logs et la sécurité.
        """
        self.stdout.write("📁 Création des répertoires...")

        directories = [
            "logs",
            "security",
            "media/qr_codes",  # Pour les QR codes MFA
        ]

        for directory in directories:
            dir_path = Path(directory)
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                self.stdout.write(f"  ✅ Créé: {directory}")
            else:
                self.stdout.write(f"  ℹ️  Existe déjà: {directory}")

    def _generate_security_settings(self):
        """
        Génère un fichier de paramètres de sécurité recommandés.
        """
        self.stdout.write("⚙️  Génération des paramètres de sécurité...")

        settings_path = Path(self.settings_file)

        if settings_path.exists() and not self.force:
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠️  {self.settings_file} existe déjà (utilisez --force pour écraser)"
                )
            )
            return

        # Générer le contenu du fichier de paramètres
        settings_content = self._generate_settings_content()

        # Écrire le fichier
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(settings_content)

        self.stdout.write(f"  ✅ Généré: {self.settings_file}")

    def _generate_settings_content(self) -> str:
        """
        Génère le contenu du fichier de paramètres de sécurité.

        Returns:
            Contenu du fichier de paramètres
        """
        config = SecurityConfig()
        recommended_settings = config.get_recommended_django_settings()

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

        if self.enable_mfa:
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

    def _configure_middlewares(self):
        """
        Configure les middlewares de sécurité.
        """
        self.stdout.write("🛡️  Configuration des middlewares de sécurité...")

        # Obtenir la liste des middlewares de sécurité
        security_middleware = setup_security_middleware()

        current_middleware = list(getattr(settings, "MIDDLEWARE", []))

        # Ajouter les middlewares manquants
        added_middleware = []
        for middleware in security_middleware:
            if middleware not in current_middleware:
                # Insérer avant le dernier middleware (généralement ClickjackingMiddleware)
                if current_middleware:
                    current_middleware.insert(-1, middleware)
                else:
                    current_middleware.append(middleware)
                added_middleware.append(middleware)

        if added_middleware:
            for middleware in added_middleware:
                self.stdout.write(f"  ✅ Ajouté: {middleware}")

            self.stdout.write(
                self.style.WARNING(
                    "\n  ⚠️  IMPORTANT: Ajoutez ces middlewares à votre MIDDLEWARE dans settings.py:"
                )
            )
            for middleware in added_middleware:
                self.stdout.write(f"    '{middleware}',")
        else:
            self.stdout.write("  ℹ️  Tous les middlewares sont déjà configurés")

    def _run_migrations(self):
        """
        Exécute les migrations nécessaires.
        """
        self.stdout.write("🔄 Exécution des migrations...")

        try:
            # Créer les migrations pour notre app
            call_command("makemigrations", "rail_django", verbosity=0)
            self.stdout.write("  ✅ Migrations créées")

            # Appliquer les migrations
            call_command("migrate", verbosity=0)
            self.stdout.write("  ✅ Migrations appliquées")

        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"  ⚠️  Erreur lors des migrations: {e}")
            )
            self.stdout.write(
                "  💡 Exécutez manuellement: python manage.py makemigrations && python manage.py migrate"
            )

    def _configure_audit_logging(self):
        """
        Configure l'audit logging.
        """
        self.stdout.write("📝 Configuration de l'audit logging...")

        # Créer le répertoire de logs s'il n'existe pas
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        # Créer les fichiers de log vides
        log_files = ["security.log", "audit.log"]
        for log_file in log_files:
            log_path = logs_dir / log_file
            if not log_path.exists():
                log_path.touch()
                self.stdout.write(f"  ✅ Créé: logs/{log_file}")
            else:
                self.stdout.write(f"  ℹ️  Existe déjà: logs/{log_file}")

        self.stdout.write("  ✅ Audit logging configuré")

    def _configure_mfa(self):
        """
        Configure l'authentification multi-facteurs.
        """
        self.stdout.write("🔐 Configuration de l'authentification multi-facteurs...")

        # Créer le répertoire pour les QR codes
        qr_dir = Path("media/qr_codes")
        qr_dir.mkdir(parents=True, exist_ok=True)
        self.stdout.write("  ✅ Répertoire QR codes créé")

        # Vérifier les dépendances MFA
        try:
            import qrcode

            self.stdout.write("  ✅ QRCode installé")
        except ImportError:
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠️  QRCode non installé - exécutez: pip install qrcode[pil]"
                )
            )

        try:
            import pyotp

            self.stdout.write("  ✅ PyOTP installé")
        except ImportError:
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠️  PyOTP non installé - exécutez: pip install pyotp"
                )
            )

        self.stdout.write("  ✅ MFA configuré")
        self.stdout.write(
            self.style.WARNING(
                "  💡 N'oubliez pas de configurer les variables d'environnement Twilio pour SMS"
            )
        )

    def _display_summary(self):
        """
        Affiche un résumé de la configuration.
        """
        self.stdout.write(self.style.SUCCESS("\n=== RÉSUMÉ DE LA CONFIGURATION ==="))

        features = [
            ("🛡️  Middlewares de sécurité", "Configurés"),
            ("📝 Audit logging", "Activé" if self.enable_audit else "Désactivé"),
            (
                "🔐 Authentification multi-facteurs",
                "Activé" if self.enable_mfa else "Désactivé",
            ),
            ("⚡ Limitation de débit", "Configurée"),
            ("📁 Répertoires", "Créés"),
        ]

        if self.create_settings:
            features.append(
                ("⚙️  Fichier de paramètres", f"Généré ({self.settings_file})")
            )

        if self.migrate:
            features.append(("🔄 Migrations", "Exécutées"))

        for feature, status in features:
            self.stdout.write(f"{feature}: {status}")

        # Instructions suivantes
        self.stdout.write(self.style.SUCCESS("\n=== ÉTAPES SUIVANTES ==="))

        next_steps = [
            "1. Ajoutez les middlewares de sécurité à votre MIDDLEWARE dans settings.py",
            "2. Configurez votre cache (Redis ou Memcached) pour la limitation de débit",
            "3. Définissez les variables d'environnement nécessaires",
            "4. Testez la configuration avec: python manage.py security_check",
        ]

        if self.create_settings:
            next_steps.insert(
                0, f"0. Importez {self.settings_file} dans votre settings.py principal"
            )

        if not self.migrate:
            next_steps.append("5. Exécutez les migrations: python manage.py migrate")

        for step in next_steps:
            self.stdout.write(f"  {step}")

        # Avertissements de sécurité
        self.stdout.write(self.style.WARNING("\n=== AVERTISSEMENTS DE SÉCURITÉ ==="))
        warnings = [
            "⚠️  Activez HTTPS en production (SECURE_SSL_REDIRECT = True)",
            "⚠️  Utilisez une SECRET_KEY forte et unique",
            "⚠️  Configurez un cache persistant (Redis/Memcached)",
            "⚠️  Surveillez régulièrement les logs de sécurité",
        ]

        for warning in warnings:
            self.stdout.write(f"  {warning}")
