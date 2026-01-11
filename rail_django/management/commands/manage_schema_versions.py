"""
Commande de gestion Django pour les versions de schéma GraphQL.
"""

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from rail_django.core.schema import get_schema_builder
from rail_django.core.schema_versioning import schema_version_manager


class Command(BaseCommand):
    """Commande pour gérer les versions de schéma GraphQL."""

    help = "Gère les versions de schéma GraphQL"

    def add_arguments(self, parser):
        """Ajoute les arguments de la commande."""
        subparsers = parser.add_subparsers(dest="action", help="Actions disponibles")

        # Créer une version
        create_parser = subparsers.add_parser(
            "create", help="Créer une nouvelle version"
        )
        create_parser.add_argument("version", help="Numéro de version (ex: 1.0.0)")
        create_parser.add_argument(
            "--description", "-d", default="", help="Description de la version"
        )
        create_parser.add_argument(
            "--created-by", default="admin", help="Créateur de la version"
        )
        create_parser.add_argument(
            "--migration-files", nargs="*", default=[], help="Fichiers de migration"
        )
        create_parser.add_argument(
            "--rollback-instructions", help="Instructions de rollback"
        )
        create_parser.add_argument(
            "--activate",
            action="store_true",
            help="Activer immédiatement cette version",
        )

        # Activer une version
        activate_parser = subparsers.add_parser("activate", help="Activer une version")
        activate_parser.add_argument("version", help="Version à activer")

        # Lister les versions
        list_parser = subparsers.add_parser("list", help="Lister les versions")
        list_parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Nombre maximum de versions à afficher",
        )
        list_parser.add_argument(
            "--format",
            choices=["table", "json"],
            default="table",
            help="Format de sortie",
        )

        # Afficher une version
        show_parser = subparsers.add_parser(
            "show", help="Afficher les détails d'une version"
        )
        show_parser.add_argument("version", help="Version à afficher")
        show_parser.add_argument(
            "--format",
            choices=["table", "json"],
            default="table",
            help="Format de sortie",
        )

        # Supprimer une version
        delete_parser = subparsers.add_parser("delete", help="Supprimer une version")
        delete_parser.add_argument("version", help="Version à supprimer")
        delete_parser.add_argument(
            "--force",
            action="store_true",
            help="Forcer la suppression sans confirmation",
        )

        # Rollback vers une version
        rollback_parser = subparsers.add_parser(
            "rollback", help="Rollback vers une version"
        )
        rollback_parser.add_argument("version", help="Version cible pour le rollback")
        rollback_parser.add_argument(
            "--force", action="store_true", help="Forcer le rollback sans confirmation"
        )

        # Comparer deux versions
        compare_parser = subparsers.add_parser("compare", help="Comparer deux versions")
        compare_parser.add_argument("version1", help="Première version")
        compare_parser.add_argument("version2", help="Deuxième version")
        compare_parser.add_argument(
            "--format",
            choices=["table", "json"],
            default="table",
            help="Format de sortie",
        )

        # Historique d'une version
        history_parser = subparsers.add_parser(
            "history", help="Afficher l'historique d'une version"
        )
        history_parser.add_argument("version", help="Version à analyser")
        history_parser.add_argument(
            "--format",
            choices=["table", "json"],
            default="table",
            help="Format de sortie",
        )

    def handle(self, *args, **options):
        """Point d'entrée principal de la commande."""
        action = options.get("action")

        if not action:
            self.print_help("manage_schema_versions", "")
            return

        try:
            if action == "create":
                self.handle_create(options)
            elif action == "activate":
                self.handle_activate(options)
            elif action == "list":
                self.handle_list(options)
            elif action == "show":
                self.handle_show(options)
            elif action == "delete":
                self.handle_delete(options)
            elif action == "rollback":
                self.handle_rollback(options)
            elif action == "compare":
                self.handle_compare(options)
            elif action == "history":
                self.handle_history(options)
            else:
                raise CommandError(f"Action inconnue: {action}")

        except Exception as e:
            raise CommandError(f"Erreur lors de l'exécution de l'action {action}: {e}")

    def handle_create(self, options):
        """Gère la création d'une nouvelle version."""
        version = options["version"]
        description = options["description"]
        created_by = options["created_by"]
        migration_files = options["migration_files"]
        rollback_instructions = options.get("rollback_instructions")
        activate = options.get("activate", False)

        self.stdout.write(f"Création de la version {version}...")

        # Construire le schéma actuel
        try:
            schema_builder = get_schema_builder("default")
            schema_builder.rebuild_schema()
            schema = schema_builder.get_schema()
        except Exception as e:
            raise CommandError(f"Erreur lors de la construction du schéma: {e}")

        # Créer la version
        try:
            schema_version = schema_version_manager.create_version(
                version=version,
                schema=schema,
                description=description,
                created_by=created_by,
                migration_files=migration_files,
                rollback_instructions=rollback_instructions,
            )

            self.stdout.write(
                self.style.SUCCESS(f"Version {version} créée avec succès")
            )

            # Activer si demandé
            if activate:
                if schema_version_manager.activate_version(version):
                    self.stdout.write(self.style.SUCCESS(f"Version {version} activée"))
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Erreur lors de l'activation de la version {version}"
                        )
                    )

        except ValueError as e:
            raise CommandError(str(e))

    def handle_activate(self, options):
        """Gère l'activation d'une version."""
        version = options["version"]

        self.stdout.write(f"Activation de la version {version}...")

        if schema_version_manager.activate_version(version):
            self.stdout.write(
                self.style.SUCCESS(f"Version {version} activée avec succès")
            )
        else:
            raise CommandError(f"Erreur lors de l'activation de la version {version}")

    def handle_list(self, options):
        """Gère l'affichage de la liste des versions."""
        limit = options["limit"]
        format_type = options["format"]

        versions = schema_version_manager.list_versions(limit=limit)

        if not versions:
            self.stdout.write("Aucune version trouvée")
            return

        if format_type == "json":
            versions_data = []
            for v in versions:
                versions_data.append(
                    {
                        "version": v.version,
                        "description": v.description,
                        "created_at": v.created_at.isoformat(),
                        "created_by": v.created_by,
                        "is_active": v.is_active,
                        "schema_hash": v.schema_hash[:12] + "...",
                    }
                )
            self.stdout.write(json.dumps(versions_data, indent=2))
        else:
            # Format tableau
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(
                f"{'Version':<15} {'Active':<8} {'Créé le':<20} {'Créé par':<15} {'Description'}"
            )
            self.stdout.write("=" * 80)

            for version in versions:
                active_status = "✓" if version.is_active else " "
                created_at = version.created_at.strftime("%Y-%m-%d %H:%M")
                description = (
                    version.description[:30] + "..."
                    if len(version.description) > 30
                    else version.description
                )

                self.stdout.write(
                    f"{version.version:<15} {active_status:<8} {created_at:<20} "
                    f"{version.created_by:<15} {description}"
                )

            self.stdout.write("=" * 80 + "\n")

    def handle_show(self, options):
        """Gère l'affichage des détails d'une version."""
        version = options["version"]
        format_type = options["format"]

        version_obj = schema_version_manager.get_version(version)
        if not version_obj:
            raise CommandError(f"Version {version} non trouvée")

        if format_type == "json":
            version_data = {
                "version": version_obj.version,
                "description": version_obj.description,
                "schema_hash": version_obj.schema_hash,
                "created_at": version_obj.created_at.isoformat(),
                "created_by": version_obj.created_by,
                "is_active": version_obj.is_active,
                "migration_files": version_obj.migration_files,
                "has_rollback_instructions": bool(version_obj.rollback_instructions),
                "metadata": version_obj.metadata,
            }
            self.stdout.write(json.dumps(version_data, indent=2))
        else:
            # Format tableau
            self.stdout.write(f"\n{'='*50}")
            self.stdout.write(f"Détails de la version {version}")
            self.stdout.write(f"{'='*50}")
            self.stdout.write(f"Version: {version_obj.version}")
            self.stdout.write(f"Description: {version_obj.description}")
            self.stdout.write(f"Hash du schéma: {version_obj.schema_hash}")
            self.stdout.write(
                f"Créé le: {version_obj.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.stdout.write(f"Créé par: {version_obj.created_by}")
            self.stdout.write(f"Active: {'Oui' if version_obj.is_active else 'Non'}")

            if version_obj.migration_files:
                self.stdout.write(f"Fichiers de migration:")
                for file in version_obj.migration_files:
                    self.stdout.write(f"  - {file}")

            if version_obj.rollback_instructions:
                self.stdout.write(f"Instructions de rollback: Disponibles")

            if version_obj.metadata:
                self.stdout.write(f"Métadonnées:")
                for key, value in version_obj.metadata.items():
                    self.stdout.write(f"  {key}: {value}")

            self.stdout.write(f"{'='*50}\n")

    def handle_delete(self, options):
        """Gère la suppression d'une version."""
        version = options["version"]
        force = options.get("force", False)

        # Vérifier si la version existe
        version_obj = schema_version_manager.get_version(version)
        if not version_obj:
            raise CommandError(f"Version {version} non trouvée")

        # Empêcher la suppression de la version active
        if version_obj.is_active:
            raise CommandError("Impossible de supprimer la version active")

        # Demander confirmation si pas forcé
        if not force:
            confirm = input(
                f"Êtes-vous sûr de vouloir supprimer la version {version}? (oui/non): "
            )
            if confirm.lower() not in ["oui", "o", "yes", "y"]:
                self.stdout.write("Suppression annulée")
                return

        if schema_version_manager.delete_version(version):
            self.stdout.write(
                self.style.SUCCESS(f"Version {version} supprimée avec succès")
            )
        else:
            raise CommandError(f"Erreur lors de la suppression de la version {version}")

    def handle_rollback(self, options):
        """Gère le rollback vers une version."""
        version = options["version"]
        force = options.get("force", False)

        # Vérifier si la version existe
        version_obj = schema_version_manager.get_version(version)
        if not version_obj:
            raise CommandError(f"Version {version} non trouvée")

        # Demander confirmation si pas forcé
        if not force:
            current_active = schema_version_manager.get_active_version()
            current_version = current_active.version if current_active else "aucune"

            confirm = input(
                f"Êtes-vous sûr de vouloir effectuer un rollback de {current_version} vers {version}? (oui/non): "
            )
            if confirm.lower() not in ["oui", "o", "yes", "y"]:
                self.stdout.write("Rollback annulé")
                return

        self.stdout.write(f"Rollback vers la version {version}...")

        if schema_version_manager.rollback_to_version(version):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Rollback vers la version {version} effectué avec succès"
                )
            )
        else:
            raise CommandError(f"Erreur lors du rollback vers la version {version}")

    def handle_compare(self, options):
        """Gère la comparaison de deux versions."""
        version1 = options["version1"]
        version2 = options["version2"]
        format_type = options["format"]

        comparison = schema_version_manager.compare_versions(version1, version2)

        if "error" in comparison:
            raise CommandError(comparison["error"])

        if format_type == "json":
            self.stdout.write(json.dumps(comparison, indent=2))
        else:
            # Format tableau
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Comparaison des versions {version1} et {version2}")
            self.stdout.write(f"{'='*60}")
            self.stdout.write(
                f"Schéma modifié: {'Oui' if comparison['schema_changed'] else 'Non'}"
            )
            self.stdout.write(f"Hash {version1}: {comparison['hash_v1'][:16]}...")
            self.stdout.write(f"Hash {version2}: {comparison['hash_v2'][:16]}...")
            self.stdout.write(f"Créé le ({version1}): {comparison['created_at_v1']}")
            self.stdout.write(f"Créé le ({version2}): {comparison['created_at_v2']}")

            if comparison["migration_files_v1"]:
                self.stdout.write(
                    f"Migrations {version1}: {', '.join(comparison['migration_files_v1'])}"
                )

            if comparison["migration_files_v2"]:
                self.stdout.write(
                    f"Migrations {version2}: {', '.join(comparison['migration_files_v2'])}"
                )

            self.stdout.write(f"{'='*60}\n")

    def handle_history(self, options):
        """Gère l'affichage de l'historique d'une version."""
        version = options["version"]
        format_type = options["format"]

        history = schema_version_manager.get_version_history(version)

        if "error" in history:
            raise CommandError(history["error"])

        if format_type == "json":
            self.stdout.write(json.dumps(history, indent=2))
        else:
            # Format tableau
            self.stdout.write(f"\n{'='*50}")
            self.stdout.write(f"Historique de la version {version}")
            self.stdout.write(f"{'='*50}")
            self.stdout.write(f"Version: {history['version']}")
            self.stdout.write(f"Description: {history['description']}")
            self.stdout.write(f"Créé le: {history['created_at']}")
            self.stdout.write(f"Créé par: {history['created_by']}")
            self.stdout.write(f"Active: {'Oui' if history['is_active'] else 'Non'}")

            if history["migration_files"]:
                self.stdout.write(f"Fichiers de migration:")
                for file in history["migration_files"]:
                    self.stdout.write(f"  - {file}")

            self.stdout.write(
                f"Instructions de rollback: {'Disponibles' if history['has_rollback_instructions'] else 'Non disponibles'}"
            )

            if history["metadata"]:
                self.stdout.write(f"Métadonnées:")
                for key, value in history["metadata"].items():
                    self.stdout.write(f"  {key}: {value}")

            self.stdout.write(f"{'='*50}\n")
