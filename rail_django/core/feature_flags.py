"""
Feature flags system for Django GraphQL Auto-Generation.

This module provides a flexible feature flags system that allows enabling/disabling
features at runtime without code changes or server restarts.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class FeatureFlagType(Enum):
    """Types de feature flags disponibles."""
    BOOLEAN = "boolean"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    LIST = "list"
    DICT = "dict"


@dataclass
class FeatureFlag:
    """
    Représente un feature flag avec ses métadonnées.

    Attributes:
        name: Nom unique du feature flag
        description: Description du feature flag
        flag_type: Type de valeur du flag
        default_value: Valeur par défaut
        enabled: Si le flag est activé
        environments: Environnements où le flag est disponible
        user_groups: Groupes d'utilisateurs concernés
        percentage_rollout: Pourcentage de déploiement (0-100)
        dependencies: Autres flags dont dépend ce flag
        metadata: Métadonnées supplémentaires
    """
    name: str
    description: str
    flag_type: FeatureFlagType
    default_value: Any
    enabled: bool = True
    environments: List[str] = field(default_factory=lambda: [
                                    'development', 'staging', 'production'])
    user_groups: List[str] = field(default_factory=list)
    percentage_rollout: int = 100
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class FeatureFlagManager:
    """
    Gestionnaire des feature flags avec support pour le cache et la configuration dynamique.
    """

    def __init__(self):
        self._flags: Dict[str, FeatureFlag] = {}
        self._cache_prefix = "feature_flag:"
        self._cache_timeout = 300  # 5 minutes
        # Ephemeral in-memory cache: {key: (value, expires_at)}
        self._runtime_cache: Dict[str, Any] = {}
        self._load_flags_from_settings()

    def _load_flags_from_settings(self) -> None:
        """Charge les feature flags depuis les settings Django."""
        try:
            flags_config = getattr(settings, 'FEATURE_FLAGS', {})

            for flag_name, flag_config in flags_config.items():
                if isinstance(flag_config, dict):
                    flag = FeatureFlag(
                        name=flag_name,
                        description=flag_config.get('description', ''),
                        flag_type=FeatureFlagType(flag_config.get('type', 'boolean')),
                        default_value=flag_config.get('default_value', False),
                        enabled=flag_config.get('enabled', True),
                        environments=flag_config.get(
                            'environments', ['development', 'staging', 'production']),
                        user_groups=flag_config.get('user_groups', []),
                        percentage_rollout=flag_config.get('percentage_rollout', 100),
                        dependencies=flag_config.get('dependencies', []),
                        metadata=flag_config.get('metadata', {})
                    )
                    self._flags[flag_name] = flag
                else:
                    # Configuration simple (boolean)
                    flag = FeatureFlag(
                        name=flag_name,
                        description=f"Feature flag for {flag_name}",
                        flag_type=FeatureFlagType.BOOLEAN,
                        default_value=bool(flag_config),
                        enabled=bool(flag_config)
                    )
                    self._flags[flag_name] = flag

        except Exception as e:
            logger.error(f"Erreur lors du chargement des feature flags: {e}")

    def is_enabled(self, flag_name: str, user=None, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Vérifie si un feature flag est activé.

        Args:
            flag_name: Nom du feature flag
            user: Utilisateur pour les vérifications de groupe
            context: Contexte supplémentaire pour l'évaluation

        Returns:
            True si le flag est activé, False sinon
        """
        # Check in-memory cache first
        cache_key = f"{self._cache_prefix}{flag_name}"
        cached_entry = self._runtime_cache.get(cache_key)

        if cached_entry is not None:
            try:
                value, expires_at = cached_entry
                if time.time() < expires_at:
                    return self._evaluate_flag_with_context(flag_name, value, user, context)
                # Expired entry; remove
                del self._runtime_cache[cache_key]
            except Exception:
                # Malformed cache entry; remove
                self._runtime_cache.pop(cache_key, None)

        # Récupérer depuis la configuration
        flag = self._flags.get(flag_name)
        if not flag:
            logger.warning(
                f"Feature flag '{flag_name}' non trouvé, utilisation de la valeur par défaut: False")
            return False

        # Vérifier les dépendances
        if not self._check_dependencies(flag):
            return False

        # Vérifier l'environnement
        current_env = getattr(settings, 'ENVIRONMENT', 'development')
        if current_env not in flag.environments:
            return False

        # Store in in-memory cache and return
        self._runtime_cache[cache_key] = (flag.enabled, time.time() + self._cache_timeout)
        return self._evaluate_flag_with_context(flag_name, flag.enabled, user, context)

    def get_value(self, flag_name: str, default=None, user=None, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Récupère la valeur d'un feature flag.

        Args:
            flag_name: Nom du feature flag
            default: Valeur par défaut si le flag n'existe pas
            user: Utilisateur pour les vérifications de groupe
            context: Contexte supplémentaire

        Returns:
            Valeur du feature flag ou valeur par défaut
        """
        flag = self._flags.get(flag_name)
        if not flag:
            return default

        if not self.is_enabled(flag_name, user, context):
            return default

        return flag.default_value

    def set_flag(self, flag_name: str, enabled: bool, cache_only: bool = False) -> None:
        """
        Active ou désactive un feature flag.

        Args:
            flag_name: Nom du feature flag
            enabled: Nouvel état du flag
            cache_only: Si True, ne modifie que le cache
        """
        cache_key = f"{self._cache_prefix}{flag_name}"
        self._runtime_cache[cache_key] = (enabled, time.time() + self._cache_timeout)

        if not cache_only and flag_name in self._flags:
            self._flags[flag_name].enabled = enabled

        logger.info(f"Feature flag '{flag_name}' {'activé' if enabled else 'désactivé'}")

    def register_flag(self, flag: FeatureFlag) -> None:
        """
        Enregistre un nouveau feature flag.

        Args:
            flag: Instance de FeatureFlag à enregistrer
        """
        self._flags[flag.name] = flag
        logger.info(f"Feature flag '{flag.name}' enregistré")

    def get_all_flags(self) -> Dict[str, FeatureFlag]:
        """
        Retourne tous les feature flags enregistrés.

        Returns:
            Dictionnaire des feature flags
        """
        return self._flags.copy()

    def clear_cache(self, flag_name: Optional[str] = None) -> None:
        """
        Vide le cache des feature flags.

        Args:
            flag_name: Nom spécifique du flag à vider, ou None pour tous
        """
        if flag_name:
            cache_key = f"{self._cache_prefix}{flag_name}"
            self._runtime_cache.pop(cache_key, None)
        else:
            # Clear all flags from in-memory cache
            self._runtime_cache.clear()

        logger.info(
            f"Cache des feature flags vidé {'pour ' + flag_name if flag_name else 'complètement'}")

    def _evaluate_flag_with_context(self, flag_name: str, base_value: bool, user=None, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Évalue un flag avec le contexte utilisateur et autres critères.

        Args:
            flag_name: Nom du flag
            base_value: Valeur de base du flag
            user: Utilisateur
            context: Contexte supplémentaire

        Returns:
            Valeur évaluée du flag
        """
        if not base_value:
            return False

        flag = self._flags.get(flag_name)
        if not flag:
            return base_value

        # Vérifier les groupes d'utilisateurs
        if flag.user_groups and user:
            user_groups = getattr(user, 'groups', None)
            if user_groups:
                user_group_names = [group.name for group in user_groups.all()]
                if not any(group in flag.user_groups for group in user_group_names):
                    return False

        # Vérifier le pourcentage de déploiement
        if flag.percentage_rollout < 100:
            import hashlib
            user_id = getattr(user, 'id', 'anonymous') if user else 'anonymous'
            hash_input = f"{flag_name}:{user_id}"
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16)
            percentage = hash_value % 100
            if percentage >= flag.percentage_rollout:
                return False

        return True

    def _check_dependencies(self, flag: FeatureFlag) -> bool:
        """
        Vérifie si toutes les dépendances d'un flag sont satisfaites.

        Args:
            flag: Feature flag à vérifier

        Returns:
            True si toutes les dépendances sont satisfaites
        """
        for dependency in flag.dependencies:
            if not self.is_enabled(dependency):
                logger.debug(f"Dépendance '{dependency}' non satisfaite pour le flag '{flag.name}'")
                return False
        return True


# Instance globale du gestionnaire de feature flags
feature_flags = FeatureFlagManager()


# Fonctions utilitaires pour un accès facile
def is_feature_enabled(flag_name: str, user=None, context: Optional[Dict[str, Any]] = None) -> bool:
    """
    Fonction utilitaire pour vérifier si un feature flag est activé.

    Args:
        flag_name: Nom du feature flag
        user: Utilisateur pour les vérifications de groupe
        context: Contexte supplémentaire

    Returns:
        True si le flag est activé, False sinon
    """
    return feature_flags.is_enabled(flag_name, user, context)


def get_feature_value(flag_name: str, default=None, user=None, context: Optional[Dict[str, Any]] = None) -> Any:
    """
    Fonction utilitaire pour récupérer la valeur d'un feature flag.

    Args:
        flag_name: Nom du feature flag
        default: Valeur par défaut
        user: Utilisateur
        context: Contexte supplémentaire

    Returns:
        Valeur du feature flag ou valeur par défaut
    """
    return feature_flags.get_value(flag_name, default, user, context)


def toggle_feature(flag_name: str, enabled: bool, cache_only: bool = False) -> None:
    """
    Fonction utilitaire pour activer/désactiver un feature flag.

    Args:
        flag_name: Nom du feature flag
        enabled: Nouvel état
        cache_only: Si True, ne modifie que le cache
    """
    feature_flags.set_flag(flag_name, enabled, cache_only)


# Décorateur pour les vues et fonctions
def feature_flag_required(flag_name: str, redirect_url: Optional[str] = None):
    """
    Décorateur pour exiger qu'un feature flag soit activé.

    Args:
        flag_name: Nom du feature flag requis
        redirect_url: URL de redirection si le flag est désactivé
    """
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            if not is_feature_enabled(flag_name, request.user if hasattr(request, 'user') else None):
                if redirect_url:
                    from django.shortcuts import redirect
                    return redirect(redirect_url)
                else:
                    from django.http import Http404
                    raise Http404("Feature not available")
            return func(request, *args, **kwargs)
        return wrapper
    return decorator
