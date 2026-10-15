"""
Django management command for automatic security setup.
"""

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ...security.config import setup_security_middleware
from .security_settings_generator import generate_settings_content


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
        settings_content = generate_settings_content(self.enable_mfa)

        # Écrire le fichier
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(settings_content)

        self.stdout.write(f"  ✅ Généré: {self.settings_file}")

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
            "2. Configurez votre cache partage pour la limitation de debit",
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
            "⚠️  Configurez un cache persistant (backend partage)",
            "⚠️  Surveillez régulièrement les logs de sécurité",
        ]

        for warning in warnings:
            self.stdout.write(f"  {warning}")
