"""
Commande de gestion Django pour vérifier la configuration de sécurité.

Cette commande vérifie :
- Configuration des middlewares de sécurité
- Paramètres d'audit
- Configuration MFA
- Limitation de débit
- Recommandations de sécurité Django
"""

import logging
from typing import Any, Dict, List

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from rail_django.security_config import SecurityConfig, get_security_status


class Command(BaseCommand):
    """
    Commande pour vérifier la configuration de sécurité GraphQL.
    """

    help = "Vérifie la configuration de sécurité GraphQL et fournit des recommandations"

    def add_arguments(self, parser):
        """
        Ajoute les arguments de la commande.

        Args:
            parser: Parser d'arguments
        """
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Tente de corriger automatiquement les problèmes détectés",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Affichage détaillé des vérifications",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Format de sortie (text ou json)",
        )

    def handle(self, *args, **options):
        """
        Exécute la commande de vérification de sécurité.

        Args:
            *args: Arguments positionnels
            **options: Options de la commande
        """
        self.verbosity = options.get("verbosity", 1)
        self.verbose = options.get("verbose", False)
        self.fix_issues = options.get("fix", False)
        self.output_format = options.get("format", "text")

        try:
            # Effectuer les vérifications de sécurité
            security_status = self._perform_security_checks()

            # Afficher les résultats
            if self.output_format == "json":
                self._output_json(security_status)
            else:
                self._output_text(security_status)

            # Retourner le code de sortie approprié
            if security_status["has_critical_issues"]:
                raise CommandError(
                    "Des problèmes critiques de sécurité ont été détectés"
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Erreur lors de la vérification de sécurité: {e}")
            )
            raise CommandError(str(e))

    def _perform_security_checks(self) -> dict[str, Any]:
        """
        Effectue toutes les vérifications de sécurité.

        Returns:
            Résultats des vérifications de sécurité
        """
        results = {
            "middleware_check": self._check_middleware_configuration(),
            "audit_check": self._check_audit_configuration(),
            "mfa_check": self._check_mfa_configuration(),
            "rate_limiting_check": self._check_rate_limiting_configuration(),
            "django_security_check": self._check_django_security_settings(),
            "database_check": self._check_database_configuration(),
            "cache_check": self._check_cache_configuration(),
            "has_critical_issues": False,
            "warnings": [],
            "recommendations": [],
        }

        # Déterminer s'il y a des problèmes critiques
        for check_name, check_result in results.items():
            if isinstance(check_result, dict) and check_result.get("critical_issues"):
                results["has_critical_issues"] = True
                break

        # Collecter tous les avertissements et recommandations
        for check_result in results.values():
            if isinstance(check_result, dict):
                results["warnings"].extend(check_result.get("warnings", []))
                results["recommendations"].extend(
                    check_result.get("recommendations", [])
                )

        return results

    def _check_middleware_configuration(self) -> dict[str, Any]:
        """
        Vérifie la configuration des middlewares de sécurité.

        Returns:
            Résultats de la vérification des middlewares
        """
        result = {
            "status": "ok",
            "warnings": [],
            "recommendations": [],
            "critical_issues": [],
        }

        middleware = getattr(settings, "MIDDLEWARE", [])

        # Vérifier la présence des middlewares de sécurité
        auth_middleware = "rail_django.middleware.GraphQLAuthenticationMiddleware"
        rate_limit_middleware = "rail_django.middleware.GraphQLRateLimitMiddleware"

        if auth_middleware not in middleware:
            result["critical_issues"].append(
                f"Middleware d'authentification manquant: {auth_middleware}"
            )

        if rate_limit_middleware not in middleware:
            result["warnings"].append(
                f"Middleware de limitation de débit manquant: {rate_limit_middleware}"
            )

        # Vérifier l'ordre des middlewares
        security_middleware = [
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            auth_middleware,
            rate_limit_middleware,
        ]

        for i, mw in enumerate(
            security_middleware[:-2]
        ):  # Exclure nos middlewares personnalisés
            if mw in middleware:
                current_index = middleware.index(mw)
                for j in range(i + 1, len(security_middleware) - 2):
                    next_mw = security_middleware[j]
                    if next_mw in middleware:
                        next_index = middleware.index(next_mw)
                        if current_index > next_index:
                            result["warnings"].append(
                                f"Ordre des middlewares incorrect: {mw} devrait être avant {next_mw}"
                            )

        if result["critical_issues"]:
            result["status"] = "critical"
        elif result["warnings"]:
            result["status"] = "warning"

        return result

    def _check_audit_configuration(self) -> dict[str, Any]:
        """
        Vérifie la configuration d'audit.

        Returns:
            Résultats de la vérification d'audit
        """
        result = {
            "status": "ok",
            "warnings": [],
            "recommendations": [],
            "critical_issues": [],
        }

        audit_config = SecurityConfig.get_audit_config()

        if not audit_config["enabled"]:
            result["warnings"].append("L'audit logging est désactivé")
        else:
            if (
                not audit_config["store_in_database"]
                and not audit_config["store_in_file"]
            ):
                result["critical_issues"].append(
                    "Aucun stockage d'audit configuré (ni base de données ni fichier)"
                )

            if audit_config["retention_days"] < 30:
                result["warnings"].append(
                    f"Période de rétention d'audit courte: {audit_config['retention_days']} jours"
                )

            # Vérifier les seuils d'alerte
            thresholds = audit_config.get("alert_thresholds", {})
            if not thresholds:
                result["recommendations"].append(
                    "Configurer des seuils d'alerte pour l'audit"
                )

        if result["critical_issues"]:
            result["status"] = "critical"
        elif result["warnings"]:
            result["status"] = "warning"

        return result

    def _check_mfa_configuration(self) -> dict[str, Any]:
        """
        Vérifie la configuration MFA.

        Returns:
            Résultats de la vérification MFA
        """
        result = {
            "status": "ok",
            "warnings": [],
            "recommendations": [],
            "critical_issues": [],
        }

        mfa_config = SecurityConfig.get_mfa_config()

        if not mfa_config["enabled"]:
            result["recommendations"].append(
                "Considérer l'activation de l'authentification multi-facteurs (MFA)"
            )
        else:
            # Vérifier la configuration SMS si activée
            if mfa_config["sms_provider"] == "twilio":
                if not mfa_config["twilio_account_sid"]:
                    result["critical_issues"].append("TWILIO_ACCOUNT_SID manquant")
                if not mfa_config["twilio_auth_token"]:
                    result["critical_issues"].append("TWILIO_AUTH_TOKEN manquant")
                if not mfa_config["twilio_from_number"]:
                    result["critical_issues"].append("TWILIO_FROM_NUMBER manquant")

            # Vérifier les paramètres de sécurité
            if mfa_config["totp_validity_window"] > 2:
                result["warnings"].append(
                    f"Fenêtre de validité TOTP large: {mfa_config['totp_validity_window']}"
                )

            if mfa_config["trusted_device_duration"] > 30:
                result["warnings"].append(
                    f"Durée de confiance des appareils longue: {mfa_config['trusted_device_duration']} jours"
                )

        if result["critical_issues"]:
            result["status"] = "critical"
        elif result["warnings"]:
            result["status"] = "warning"

        return result

    def _check_rate_limiting_configuration(self) -> dict[str, Any]:
        """
        Vérifie la configuration de limitation de débit.

        Returns:
            Résultats de la vérification de limitation de débit
        """
        result = {
            "status": "ok",
            "warnings": [],
            "recommendations": [],
            "critical_issues": [],
        }

        middleware_config = SecurityConfig.get_middleware_config()

        if not middleware_config["enable_rate_limiting"]:
            result["warnings"].append("La limitation de débit est désactivée")
        else:
            # Vérifier les limites configurées
            login_limit = middleware_config["login_attempts_limit"]
            if login_limit > 10:
                result["warnings"].append(
                    f"Limite de tentatives de connexion élevée: {login_limit}"
                )

            graphql_limit = middleware_config["graphql_requests_limit"]
            if graphql_limit > 1000:
                result["warnings"].append(
                    f"Limite de requêtes GraphQL élevée: {graphql_limit}"
                )

        if result["critical_issues"]:
            result["status"] = "critical"
        elif result["warnings"]:
            result["status"] = "warning"

        return result

    def _check_django_security_settings(self) -> dict[str, Any]:
        """
        Vérifie les paramètres de sécurité Django.

        Returns:
            Résultats de la vérification des paramètres Django
        """
        result = {
            "status": "ok",
            "warnings": [],
            "recommendations": [],
            "critical_issues": [],
        }

        # Vérifications critiques
        if getattr(settings, "DEBUG", False):
            result["critical_issues"].append("DEBUG est activé en production")

        if not getattr(settings, "SECRET_KEY", "") or len(settings.SECRET_KEY) < 32:
            result["critical_issues"].append("SECRET_KEY manquante ou trop courte")

        # Vérifications de sécurité HTTPS
        if not getattr(settings, "SECURE_SSL_REDIRECT", False):
            result["warnings"].append("SECURE_SSL_REDIRECT non activé")

        if not getattr(settings, "SESSION_COOKIE_SECURE", False):
            result["warnings"].append("SESSION_COOKIE_SECURE non activé")

        if not getattr(settings, "CSRF_COOKIE_SECURE", False):
            result["warnings"].append("CSRF_COOKIE_SECURE non activé")

        # Vérifications des headers de sécurité
        if not getattr(settings, "SECURE_BROWSER_XSS_FILTER", False):
            result["recommendations"].append("Activer SECURE_BROWSER_XSS_FILTER")

        if not getattr(settings, "SECURE_CONTENT_TYPE_NOSNIFF", False):
            result["recommendations"].append("Activer SECURE_CONTENT_TYPE_NOSNIFF")

        if result["critical_issues"]:
            result["status"] = "critical"
        elif result["warnings"]:
            result["status"] = "warning"

        return result

    def _check_database_configuration(self) -> dict[str, Any]:
        """
        Vérifie la configuration de la base de données.

        Returns:
            Résultats de la vérification de la base de données
        """
        result = {
            "status": "ok",
            "warnings": [],
            "recommendations": [],
            "critical_issues": [],
        }

        try:
            # Tester la connexion à la base de données
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

            # Vérifier si les tables d'audit existent
            table_names = connection.introspection.table_names()

            audit_tables = [
                "rail_django_auditeventmodel",
                "rail_django_mfadevice",
                "rail_django_mfabackupcode",
                "rail_django_trusteddevice",
            ]

            missing_tables = [
                table for table in audit_tables if table not in table_names
            ]
            if missing_tables:
                result["warnings"].append(
                    f"Tables d'audit manquantes: {', '.join(missing_tables)}"
                )
                result["recommendations"].append(
                    "Exécuter les migrations: python manage.py migrate"
                )

        except Exception as e:
            result["critical_issues"].append(
                f"Erreur de connexion à la base de données: {e}"
            )

        if result["critical_issues"]:
            result["status"] = "critical"
        elif result["warnings"]:
            result["status"] = "warning"

        return result

    def _check_cache_configuration(self) -> dict[str, Any]:
        """
        Vérifie la configuration du cache (sans dépendance au cache Django).

        Returns:
            Résultats de la vérification du cache
        """
        result = {
            "status": "ok",
            "warnings": [],
            "recommendations": [],
            "critical_issues": [],
        }

        try:
            # Vérifier la configuration du cache dans settings
            cache_config = getattr(settings, "CACHES", {})
            default_cache = cache_config.get("default", {})

            backend = default_cache.get("BACKEND")

            if backend:
                # Le projet utilise désormais des caches en mémoire par processus.
                # Les backends externes ne sont généralement pas nécessaires.
                if backend not in (
                    "django.core.cache.backends.dummy.DummyCache",
                    "django.core.cache.backends.locmem.LocMemCache",
                ):
                    result["warnings"].append(
                        "Backend de cache Django externe détecté. Le projet utilise des caches en mémoire; "
                        "vérifiez que ce backend est réellement requis"
                    )
                elif backend == "django.core.cache.backends.dummy.DummyCache":
                    result["warnings"].append(
                        "Backend DummyCache utilisé. Assurez-vous que l'absence de cache persistant est intentionnelle"
                    )
                else:
                    result["recommendations"].append(
                        "LocMemCache détecté. Cela convient aux environnements de développement; pour la production, "
                        "évaluez si un backend persistant est nécessaire (souvent non requis ici)"
                    )
            else:
                result["recommendations"].append(
                    "Aucun backend de cache Django configuré. Le projet fonctionne avec des caches en mémoire par "
                    "processus — configuration acceptable"
                )

        except Exception as e:
            result["critical_issues"].append(f"Erreur de configuration du cache: {e}")

        if result["critical_issues"]:
            result["status"] = "critical"
        elif result["warnings"]:
            result["status"] = "warning"

        return result

    def _output_text(self, security_status: dict[str, Any]):
        """
        Affiche les résultats au format texte.

        Args:
            security_status: Statut de sécurité
        """
        self.stdout.write(
            self.style.SUCCESS("=== VÉRIFICATION DE SÉCURITÉ GRAPHQL ===\n")
        )

        # Afficher le résumé
        if security_status["has_critical_issues"]:
            self.stdout.write(self.style.ERROR("❌ PROBLÈMES CRITIQUES DÉTECTÉS"))
        elif security_status["warnings"]:
            self.stdout.write(self.style.WARNING("⚠️  AVERTISSEMENTS DÉTECTÉS"))
        else:
            self.stdout.write(self.style.SUCCESS("✅ CONFIGURATION SÉCURISÉE"))

        self.stdout.write("")

        # Afficher les détails de chaque vérification
        checks = [
            ("middleware_check", "Configuration des Middlewares"),
            ("audit_check", "Configuration d'Audit"),
            ("mfa_check", "Configuration MFA"),
            ("rate_limiting_check", "Limitation de Débit"),
            ("django_security_check", "Paramètres de Sécurité Django"),
            ("database_check", "Configuration Base de Données"),
            ("cache_check", "Configuration Cache"),
        ]

        for check_key, check_name in checks:
            check_result = security_status[check_key]
            self._output_check_result(check_name, check_result)

        # Afficher les recommandations globales
        if security_status["recommendations"]:
            self.stdout.write(self.style.SUCCESS("\n=== RECOMMANDATIONS ==="))
            for recommendation in set(security_status["recommendations"]):
                self.stdout.write(f"💡 {recommendation}")

    def _output_check_result(self, check_name: str, result: dict[str, Any]):
        """
        Affiche le résultat d'une vérification.

        Args:
            check_name: Nom de la vérification
            result: Résultat de la vérification
        """
        status = result["status"]

        if status == "critical":
            status_icon = "❌"
            status_style = self.style.ERROR
        elif status == "warning":
            status_icon = "⚠️"
            status_style = self.style.WARNING
        else:
            status_icon = "✅"
            status_style = self.style.SUCCESS

        self.stdout.write(status_style(f"{status_icon} {check_name}"))

        if self.verbose or result["critical_issues"] or result["warnings"]:
            for issue in result["critical_issues"]:
                self.stdout.write(f"  🔴 CRITIQUE: {issue}")

            for warning in result["warnings"]:
                self.stdout.write(f"  🟡 AVERTISSEMENT: {warning}")

            for recommendation in result["recommendations"]:
                self.stdout.write(f"  💡 RECOMMANDATION: {recommendation}")

        self.stdout.write("")

    def _output_json(self, security_status: dict[str, Any]):
        """
        Affiche les résultats au format JSON.

        Args:
            security_status: Statut de sécurité
        """
        import json

        self.stdout.write(json.dumps(security_status, indent=2, ensure_ascii=False))
