"""
Système de versioning pour les schémas GraphQL
Gère les versions de schéma, les migrations et les rollbacks.
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import graphene
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from graphene import Schema

logger = logging.getLogger(__name__)


@dataclass
class SchemaVersion:
    """Représente une version de schéma GraphQL."""

    version: str
    description: str
    schema_hash: str
    created_at: datetime
    created_by: str
    migration_files: List[str]
    rollback_instructions: Optional[str] = None
    is_active: bool = False
    metadata: Optional[Dict[str, Any]] = None


class SchemaVersionModel(models.Model):
    """Modèle Django pour stocker les versions de schéma."""

    version = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    schema_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100)
    migration_files = models.JSONField(default=list)
    rollback_instructions = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "rail_django_schema_versions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Schema v{self.version} ({'active' if self.is_active else 'inactive'})"


class SchemaVersionManager:
    """Gestionnaire des versions de schéma GraphQL."""

    def __init__(self):
        self.cache_key_prefix = "graphql_schema_version"
        self.cache_timeout = getattr(settings, "GRAPHQL_SCHEMA_CACHE_TIMEOUT", 3600)
        # In-memory per-process cache: {key: (schema_version_dict, expires_ts)}
        self._version_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

    def generate_schema_hash(self, schema: Schema) -> str:
        """Génère un hash unique pour un schéma GraphQL."""
        try:
            # Obtenir la représentation SDL du schéma
            schema_sdl = str(schema)

            # Créer un hash SHA-256
            return hashlib.sha256(schema_sdl.encode("utf-8")).hexdigest()

        except Exception as e:
            logger.error(f"Erreur lors de la génération du hash de schéma: {e}")
            # Fallback: utiliser un hash basé sur les types
            type_names = sorted([str(t) for t in schema.get_type_map().keys()])
            content = "".join(type_names)
            return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def create_version(
        self,
        version: str,
        schema: Schema,
        description: str = "",
        created_by: str = "system",
        migration_files: Optional[List[str]] = None,
        rollback_instructions: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SchemaVersion:
        """Crée une nouvelle version de schéma."""

        schema_hash = self.generate_schema_hash(schema)
        migration_files = migration_files or []
        metadata = metadata or {}

        # Vérifier si cette version existe déjà
        if self.version_exists(version):
            raise ValueError(f"La version {version} existe déjà")

        # Vérifier si le schéma a changé
        current_active = self.get_active_version()
        if current_active and current_active.schema_hash == schema_hash:
            logger.warning(
                f"Le schéma n'a pas changé depuis la version {current_active.version}"
            )

        with transaction.atomic():
            # Créer l'enregistrement en base
            version_model = SchemaVersionModel.objects.create(
                version=version,
                description=description,
                schema_hash=schema_hash,
                created_by=created_by,
                migration_files=migration_files,
                rollback_instructions=rollback_instructions,
                metadata=metadata,
            )

            # Créer l'objet SchemaVersion
            schema_version = SchemaVersion(
                version=version,
                description=description,
                schema_hash=schema_hash,
                created_at=version_model.created_at,
                created_by=created_by,
                migration_files=migration_files,
                rollback_instructions=rollback_instructions,
                metadata=metadata,
            )

            # Sauvegarder le schéma sur disque
            self._save_schema_to_file(schema, version)

            # Invalider le cache
            self._invalidate_cache()

            logger.info(f"Version de schéma {version} créée avec succès")
            return schema_version

    def activate_version(self, version: str) -> bool:
        """Active une version spécifique du schéma."""
        try:
            with transaction.atomic():
                # Désactiver toutes les versions
                SchemaVersionModel.objects.update(is_active=False)

                # Activer la version spécifiée
                version_model = SchemaVersionModel.objects.get(version=version)
                version_model.is_active = True
                version_model.save()

                # Invalider le cache
                self._invalidate_cache()

                logger.info(f"Version {version} activée avec succès")
                return True

        except SchemaVersionModel.DoesNotExist:
            logger.error(f"Version {version} non trouvée")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de l'activation de la version {version}: {e}")
            return False

    def get_active_version(self) -> Optional[SchemaVersion]:
        """Récupère la version active du schéma."""
        cache_key = f"{self.cache_key_prefix}_active"
        cached = self._version_cache.get(cache_key)
        if cached:
            cached_version, expires_ts = cached
            if timezone.now().timestamp() < expires_ts:
                return SchemaVersion(**cached_version)

        try:
            version_model = SchemaVersionModel.objects.filter(is_active=True).first()
            if not version_model:
                return None

            schema_version = SchemaVersion(
                version=version_model.version,
                description=version_model.description,
                schema_hash=version_model.schema_hash,
                created_at=version_model.created_at,
                created_by=version_model.created_by,
                migration_files=version_model.migration_files,
                rollback_instructions=version_model.rollback_instructions,
                is_active=version_model.is_active,
                metadata=version_model.metadata,
            )

            # Mettre en cache (in-memory)
            self._version_cache[cache_key] = (
                asdict(schema_version),
                timezone.now().timestamp() + float(self.cache_timeout),
            )

            return schema_version

        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la version active: {e}")
            return None

    def get_version(self, version: str) -> Optional[SchemaVersion]:
        """Récupère une version spécifique du schéma."""
        cache_key = f"{self.cache_key_prefix}_{version}"
        cached = self._version_cache.get(cache_key)
        if cached:
            cached_version, expires_ts = cached
            if timezone.now().timestamp() < expires_ts:
                return SchemaVersion(**cached_version)

        try:
            version_model = SchemaVersionModel.objects.get(version=version)

            schema_version = SchemaVersion(
                version=version_model.version,
                description=version_model.description,
                schema_hash=version_model.schema_hash,
                created_at=version_model.created_at,
                created_by=version_model.created_by,
                migration_files=version_model.migration_files,
                rollback_instructions=version_model.rollback_instructions,
                is_active=version_model.is_active,
                metadata=version_model.metadata,
            )

            # Mettre en cache (in-memory)
            self._version_cache[cache_key] = (
                asdict(schema_version),
                timezone.now().timestamp() + float(self.cache_timeout),
            )

            return schema_version

        except SchemaVersionModel.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la version {version}: {e}")
            return None

    def list_versions(self, limit: int = 50) -> List[SchemaVersion]:
        """Liste toutes les versions de schéma."""
        try:
            version_models = SchemaVersionModel.objects.all()[:limit]

            versions = []
            for model in version_models:
                versions.append(
                    SchemaVersion(
                        version=model.version,
                        description=model.description,
                        schema_hash=model.schema_hash,
                        created_at=model.created_at,
                        created_by=model.created_by,
                        migration_files=model.migration_files,
                        rollback_instructions=model.rollback_instructions,
                        is_active=model.is_active,
                        metadata=model.metadata,
                    )
                )

            return versions

        except Exception as e:
            logger.error(f"Erreur lors de la liste des versions: {e}")
            return []

    def version_exists(self, version: str) -> bool:
        """Vérifie si une version existe."""
        return SchemaVersionModel.objects.filter(version=version).exists()

    def delete_version(self, version: str) -> bool:
        """Supprime une version de schéma."""
        try:
            with transaction.atomic():
                version_model = SchemaVersionModel.objects.get(version=version)

                # Empêcher la suppression de la version active
                if version_model.is_active:
                    raise ValueError("Impossible de supprimer la version active")

                # Supprimer le fichier de schéma
                self._delete_schema_file(version)

                # Supprimer l'enregistrement
                version_model.delete()

                # Invalider le cache
                self._invalidate_cache()

                logger.info(f"Version {version} supprimée avec succès")
                return True

        except SchemaVersionModel.DoesNotExist:
            logger.error(f"Version {version} non trouvée")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de la suppression de la version {version}: {e}")
            return False

    def rollback_to_version(self, version: str) -> bool:
        """Effectue un rollback vers une version spécifique."""
        try:
            target_version = self.get_version(version)
            if not target_version:
                logger.error(f"Version {version} non trouvée pour le rollback")
                return False

            # Charger le schéma depuis le fichier
            schema = self._load_schema_from_file(version)
            if not schema:
                logger.error(
                    f"Impossible de charger le schéma pour la version {version}"
                )
                return False

            # Activer la version
            success = self.activate_version(version)

            if success:
                logger.info(f"Rollback vers la version {version} effectué avec succès")

                # Exécuter les instructions de rollback si disponibles
                if target_version.rollback_instructions:
                    logger.info("Exécution des instructions de rollback...")
                    # Ici, vous pourriez exécuter des commandes de rollback personnalisées

            return success

        except Exception as e:
            logger.error(f"Erreur lors du rollback vers la version {version}: {e}")
            return False

    def compare_versions(self, version1: str, version2: str) -> Dict[str, Any]:
        """Compare deux versions de schéma."""
        v1 = self.get_version(version1)
        v2 = self.get_version(version2)

        if not v1 or not v2:
            return {"error": "Une ou plusieurs versions non trouvées"}

        return {
            "version1": version1,
            "version2": version2,
            "schema_changed": v1.schema_hash != v2.schema_hash,
            "hash_v1": v1.schema_hash,
            "hash_v2": v2.schema_hash,
            "created_at_v1": v1.created_at.isoformat(),
            "created_at_v2": v2.created_at.isoformat(),
            "migration_files_v1": v1.migration_files,
            "migration_files_v2": v2.migration_files,
        }

    def get_version_history(self, version: str) -> Dict[str, Any]:
        """Récupère l'historique d'une version."""
        version_obj = self.get_version(version)
        if not version_obj:
            return {"error": "Version non trouvée"}

        return {
            "version": version_obj.version,
            "description": version_obj.description,
            "created_at": version_obj.created_at.isoformat(),
            "created_by": version_obj.created_by,
            "is_active": version_obj.is_active,
            "migration_files": version_obj.migration_files,
            "has_rollback_instructions": bool(version_obj.rollback_instructions),
            "metadata": version_obj.metadata,
        }

    def _save_schema_to_file(self, schema: Schema, version: str):
        """Sauvegarde un schéma dans un fichier."""
        try:
            schema_dir = Path(settings.BASE_DIR) / "schema_versions"
            schema_dir.mkdir(exist_ok=True)

            schema_file = schema_dir / f"schema_v{version}.graphql"

            with open(schema_file, "w", encoding="utf-8") as f:
                f.write(str(schema))

            logger.debug(f"Schéma sauvegardé dans {schema_file}")

        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du schéma: {e}")

    def _load_schema_from_file(self, version: str) -> Optional[str]:
        """Charge un schéma depuis un fichier."""
        try:
            schema_dir = Path(settings.BASE_DIR) / "schema_versions"
            schema_file = schema_dir / f"schema_v{version}.graphql"

            if not schema_file.exists():
                return None

            with open(schema_file, "r", encoding="utf-8") as f:
                return f.read()

        except Exception as e:
            logger.error(f"Erreur lors du chargement du schéma: {e}")
            return None

    def _delete_schema_file(self, version: str):
        """Supprime le fichier de schéma."""
        try:
            schema_dir = Path(settings.BASE_DIR) / "schema_versions"
            schema_file = schema_dir / f"schema_v{version}.graphql"

            if schema_file.exists():
                schema_file.unlink()
                logger.debug(f"Fichier de schéma supprimé: {schema_file}")

        except Exception as e:
            logger.error(f"Erreur lors de la suppression du fichier de schéma: {e}")

    def _invalidate_cache(self):
        """Invalide le cache des versions."""
        try:
            # Clear in-memory cache entirely
            self._version_cache.clear()
        except Exception as e:
            logger.error(f"Erreur lors de l'invalidation du cache: {e}")


# Instance globale du gestionnaire de versions
schema_version_manager = SchemaVersionManager()
