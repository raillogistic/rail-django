"""
Système de permissions au niveau des champs pour Django GraphQL.

Ce module fournit :
- Permissions dynamiques par champ
- Filtrage basé sur les relations
- Masquage conditionnel des champs
- Validation des accès en temps réel
"""

import logging
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

from django.contrib.auth import get_user_model
from django.db import models
from graphene import Field, ObjectType
from graphql import GraphQLError

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
logger = logging.getLogger(__name__)


class FieldAccessLevel(Enum):
    """Niveaux d'accès aux champs."""

    NONE = "none"  # Aucun accès
    READ = "read"  # Lecture seule
    WRITE = "write"  # Lecture et écriture
    ADMIN = "admin"  # Accès administrateur


class FieldVisibility(Enum):
    """Visibilité des champs."""

    VISIBLE = "visible"  # Champ visible
    HIDDEN = "hidden"  # Champ masqué
    MASKED = "masked"  # Champ masqué avec valeur par défaut
    REDACTED = "redacted"  # Champ censuré (ex: ****)


@dataclass
class FieldPermissionRule:
    """Règle de permission pour un champ."""

    field_name: str
    model_name: str
    access_level: FieldAccessLevel
    visibility: FieldVisibility
    condition: Optional[Callable] = None
    mask_value: Any = None
    roles: List[str] = None
    permissions: List[str] = None
    context_required: bool = False


@dataclass
class FieldContext:
    """Contexte d'accès à un champ."""

    user: "AbstractUser"
    instance: Optional[models.Model] = None
    parent_instance: Optional[models.Model] = None
    field_name: str = None
    operation_type: str = "read"  # read, write, create, update, delete
    request_context: Dict[str, Any] = None
    model_class: Optional[Type[models.Model]] = None


class FieldPermissionManager:
    """
    Gestionnaire des permissions au niveau des champs.
    """

    def __init__(self):
        """Initialise le gestionnaire de permissions de champs."""
        self._field_rules: Dict[str, List[FieldPermissionRule]] = {}
        self._global_rules: List[FieldPermissionRule] = []
        self._graphql_configs: Set[str] = set()
        self._sensitive_fields = {
            "password",
            "token",
            "secret",
            "key",
            "hash",
            "ssn",
            "social_security",
            "credit_card",
            "bank_account",
        }

        # Règles par défaut pour les champs sensibles
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Configure les règles par défaut pour les champs sensibles."""
        # Champs de mot de passe - toujours masqués
        self.register_field_rule(
            FieldPermissionRule(
                field_name="password",
                model_name="*",
                access_level=FieldAccessLevel.NONE,
                visibility=FieldVisibility.HIDDEN,
                roles=["admin", "superadmin"],
            )
        )

        # Champs de token - visibles seulement pour l'admin
        self.register_field_rule(
            FieldPermissionRule(
                field_name="*token*",
                model_name="*",
                access_level=FieldAccessLevel.READ,
                visibility=FieldVisibility.MASKED,
                mask_value="***HIDDEN***",
                roles=["admin", "superadmin"],
            )
        )

        # Email - visible pour le propriétaire et admin
        self.register_field_rule(
            FieldPermissionRule(
                field_name="email",
                model_name="User",
                access_level=FieldAccessLevel.READ,
                visibility=FieldVisibility.VISIBLE,
                condition=self._is_owner_or_admin,
            )
        )

        # Champs financiers - accès restreint
        for field in ["salary", "wage", "income", "revenue", "cost", "price"]:
            self.register_field_rule(
                FieldPermissionRule(
                    field_name=field,
                    model_name="*",
                    access_level=FieldAccessLevel.READ,
                    visibility=FieldVisibility.MASKED,
                    mask_value="***CONFIDENTIAL***",
                    roles=["manager", "admin", "superadmin"],
                )
            )

    def register_field_rule(self, rule: FieldPermissionRule):
        """
        Enregistre une règle de permission pour un champ.

        Args:
            rule: Règle de permission à enregistrer
        """
        key = f"{rule.model_name}.{rule.field_name}"

        if key not in self._field_rules:
            self._field_rules[key] = []

        self._field_rules[key].append(rule)
        logger.info(f"Règle de permission enregistrée pour {key}")

    def register_global_rule(self, rule: FieldPermissionRule):
        """
        Enregistre une règle globale applicable à tous les modèles.

        Args:
            rule: Règle globale à enregistrer
        """
        self._global_rules.append(rule)
        logger.info(f"Règle globale enregistrée pour {rule.field_name}")

    def register_graphql_field_config(
        self, model_class: Type[models.Model], graphql_meta: Any
    ) -> None:
        """Crée des règles basées sur la configuration GraphQL d'un modèle."""

        if not model_class or not graphql_meta:
            return

        model_label = model_class._meta.label_lower
        if model_label in self._graphql_configs:
            return

        field_config = getattr(graphql_meta, "field_config", None)
        if not field_config:
            return

        def _rules_from_fields(field_names, access, visibility, mask_value=None):
            for field_name in field_names:
                rule = FieldPermissionRule(
                    field_name=field_name,
                    model_name=model_label,
                    access_level=access,
                    visibility=visibility,
                    mask_value=mask_value,
                )
                self.register_field_rule(rule)

        if field_config.exclude:
            _rules_from_fields(
                field_config.exclude,
                FieldAccessLevel.NONE,
                FieldVisibility.HIDDEN,
            )

        if field_config.read_only:
            _rules_from_fields(
                field_config.read_only,
                FieldAccessLevel.READ,
                FieldVisibility.VISIBLE,
            )

        if field_config.write_only:
            _rules_from_fields(
                field_config.write_only,
                FieldAccessLevel.WRITE,
                FieldVisibility.HIDDEN,
            )

        self._graphql_configs.add(model_label)

    def _get_model_lookup_tokens(
        self, instance: Optional[models.Model], model_class: Optional[Type[models.Model]]
    ) -> List[str]:
        """Retourne les identifiants possibles (label + nom) pour un modèle."""

        tokens: List[str] = []
        target_class = None
        if instance is not None:
            target_class = instance.__class__
        elif model_class is not None:
            target_class = model_class

        if target_class is not None:
            tokens.extend([
                target_class._meta.label_lower,
                target_class.__name__,
            ])

        tokens.append("*")

        seen_tokens: List[str] = []
        for token in tokens:
            if token and token not in seen_tokens:
                seen_tokens.append(token)

        return seen_tokens

    def get_field_access_level(self, context: FieldContext) -> FieldAccessLevel:
        """
        Détermine le niveau d'accès pour un champ.

        Args:
            context: Contexte d'accès au champ

        Returns:
            Niveau d'accès autorisé
        """
        if not context.user or not context.user.is_authenticated:
            return FieldAccessLevel.NONE

        # Super utilisateur a accès à tout
        if context.user.is_superuser:
            return FieldAccessLevel.ADMIN

        # Vérifier les règles spécifiques au champ
        field_name = context.field_name
        lookup_tokens = self._get_model_lookup_tokens(
            context.instance, context.model_class
        )

        search_keys: List[str] = []
        seen: Set[str] = set()
        for token in lookup_tokens:
            for suffix in (field_name, "*"):
                key = f"{token}.{suffix}"
                if key not in seen:
                    search_keys.append(key)
                    seen.add(key)

        for key in search_keys:
            if key in self._field_rules:
                for rule in self._field_rules[key]:
                    if self._rule_applies(rule, context):
                        return rule.access_level

        # Vérifier les règles globales
        for rule in self._global_rules:
            if self._rule_applies(rule, context):
                return rule.access_level

        # Accès par défaut basé sur les permissions Django
        target_model = context.model_class
        if target_model is None and context.instance is not None:
            target_model = context.instance.__class__

        if target_model is not None:
            app_label = target_model._meta.app_label
            model_name_lower = target_model._meta.model_name

            if context.operation_type in ["create", "update", "delete"]:
                perm_name = f"{app_label}.change_{model_name_lower}"
                if context.user.has_perm(perm_name):
                    return FieldAccessLevel.WRITE

            perm_name = f"{app_label}.view_{model_name_lower}"
            if context.user.has_perm(perm_name):
                return FieldAccessLevel.READ

        # Fallback: permettre la lecture si aucune règle spécifique n'existe
        return FieldAccessLevel.READ

    def get_field_visibility(
        self, context: FieldContext
    ) -> Tuple[FieldVisibility, Any]:
        """
        Détermine la visibilité d'un champ et sa valeur masquée si applicable.

        Args:
            context: Contexte d'accès au champ

        Returns:
            Tuple (visibilité, valeur_masquée)
        """
        access_level = self.get_field_access_level(context)

        if access_level == FieldAccessLevel.NONE:
            return FieldVisibility.HIDDEN, None

        # Vérifier les règles spécifiques de visibilité
        field_name = context.field_name
        lookup_tokens = self._get_model_lookup_tokens(
            context.instance, context.model_class
        )

        search_keys: List[str] = []
        seen: Set[str] = set()
        for token in lookup_tokens:
            for suffix in (field_name, "*"):
                key = f"{token}.{suffix}"
                if key not in seen:
                    search_keys.append(key)
                    seen.add(key)

        for key in search_keys:
            if key in self._field_rules:
                for rule in self._field_rules[key]:
                    if self._rule_applies(rule, context):
                        return rule.visibility, rule.mask_value

        # Vérifier si c'est un champ sensible
        if self._is_sensitive_field(field_name):
            return FieldVisibility.MASKED, "***HIDDEN***"

        return FieldVisibility.VISIBLE, None

    def _rule_applies(self, rule: FieldPermissionRule, context: FieldContext) -> bool:
        """
        Vérifie si une règle s'applique au contexte donné.

        Args:
            rule: Règle à vérifier
            context: Contexte d'accès

        Returns:
            True si la règle s'applique
        """
        # Vérifier le nom du modèle
        if rule.model_name not in ("*", None):
            identifiers = self._get_model_lookup_tokens(
                context.instance, context.model_class
            )
            if rule.model_name not in identifiers:
                return False

        # Vérifier le nom du champ (support des wildcards)
        if rule.field_name != "*":
            if "*" in rule.field_name:
                # Support des wildcards simples
                pattern = rule.field_name.replace("*", "")
                if pattern not in context.field_name:
                    return False
            elif rule.field_name != context.field_name:
                return False

        # Vérifier les rôles
        if rule.roles:
            from .rbac import role_manager

            user_roles = role_manager.get_user_roles(context.user)
            if not any(role in user_roles for role in rule.roles):
                return False

        # Vérifier les permissions
        if rule.permissions:
            if not any(context.user.has_perm(perm) for perm in rule.permissions):
                return False

        # Vérifier la condition personnalisée
        if rule.condition:
            try:
                if not rule.condition(context):
                    return False
            except Exception as e:
                logger.error(f"Erreur dans la condition de règle: {e}")
                return False

        return True

    def _is_sensitive_field(self, field_name: str) -> bool:
        """
        Vérifie si un champ est considéré comme sensible.

        Args:
            field_name: Nom du champ

        Returns:
            True si le champ est sensible
        """
        field_lower = field_name.lower()
        return any(sensitive in field_lower for sensitive in self._sensitive_fields)

    def _is_owner_or_admin(self, context: FieldContext) -> bool:
        """
        Vérifie si l'utilisateur est propriétaire de l'objet ou administrateur.

        Args:
            context: Contexte d'accès

        Returns:
            True si l'utilisateur est propriétaire ou admin
        """
        if context.user.is_staff or context.user.is_superuser:
            return True

        if context.instance:
            # Vérifier si l'utilisateur est le propriétaire
            if hasattr(context.instance, "owner"):
                return context.instance.owner == context.user
            elif hasattr(context.instance, "created_by"):
                return context.instance.created_by == context.user
            elif hasattr(context.instance, "user"):
                return context.instance.user == context.user
            elif isinstance(context.instance, get_user_model()):
                return context.instance == context.user

        return False

    def filter_fields_for_user(
        self, user: "AbstractUser", model_class: type, instance: models.Model = None
    ) -> Dict[str, Any]:
        """
        Filtre les champs visibles pour un utilisateur.

        Args:
            user: Utilisateur
            model_class: Classe du modèle
            instance: Instance du modèle (optionnel)

        Returns:
            Dictionnaire des champs et leurs métadonnées d'accès
        """
        result = {}

        # Obtenir tous les champs du modèle
        for field in model_class._meta.get_fields():
            if field.name.startswith("_"):
                continue  # Ignorer les champs privés

            context = FieldContext(
                user=user,
                instance=instance,
                field_name=field.name,
                operation_type="read",
                model_class=model_class,
            )

            access_level = self.get_field_access_level(context)
            visibility, mask_value = self.get_field_visibility(context)

            if visibility != FieldVisibility.HIDDEN:
                result[field.name] = {
                    "access_level": access_level.value,
                    "visibility": visibility.value,
                    "mask_value": mask_value,
                    "readable": access_level
                    in [
                        FieldAccessLevel.READ,
                        FieldAccessLevel.WRITE,
                        FieldAccessLevel.ADMIN,
                    ],
                    "writable": access_level
                    in [FieldAccessLevel.WRITE, FieldAccessLevel.ADMIN],
                }

        return result

    def apply_field_filtering(
        self, queryset: models.QuerySet, user: "AbstractUser"
    ) -> models.QuerySet:
        """
        Applique le filtrage des champs à un QuerySet.

        Args:
            queryset: QuerySet à filtrer
            user: Utilisateur

        Returns:
            QuerySet filtré
        """
        if not user or not user.is_authenticated:
            return queryset.none()

        # Super utilisateur voit tout
        if user.is_superuser:
            return queryset

        model_class = queryset.model
        allowed_fields = self.filter_fields_for_user(user, model_class)

        # Construire la liste des champs à exclure
        exclude_fields = []
        for field in model_class._meta.get_fields():
            if field.name not in allowed_fields:
                exclude_fields.append(field.name)

        # Appliquer le filtrage (cette partie dépend de votre implémentation GraphQL)
        # Pour l'instant, on retourne le queryset tel quel
        # Dans une vraie implémentation, vous devriez intégrer cela avec votre résolveur GraphQL

        return queryset


def field_permission_required(
    field_name: str, access_level: FieldAccessLevel = FieldAccessLevel.READ
):
    """
    Décorateur pour vérifier les permissions d'accès à un champ.

    Args:
        field_name: Nom du champ
        access_level: Niveau d'accès requis

    Returns:
        Décorateur de vérification de permission
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extraire le contexte GraphQL
            info = None
            instance = None

            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                elif isinstance(arg, models.Model):
                    instance = arg

            if not info or not hasattr(info.context, "user"):
                raise GraphQLError("Contexte utilisateur non disponible")

            user = info.context.user
            if not user or not user.is_authenticated:
                raise GraphQLError("Authentification requise")

            context = FieldContext(
                user=user,
                instance=instance,
                field_name=field_name,
                operation_type="read",
                model_class=model_class,
            )

            user_access_level = field_permission_manager.get_field_access_level(context)

            # Vérifier le niveau d'accès
            access_levels_hierarchy = {
                FieldAccessLevel.NONE: 0,
                FieldAccessLevel.READ: 1,
                FieldAccessLevel.WRITE: 2,
                FieldAccessLevel.ADMIN: 3,
            }

            if (
                access_levels_hierarchy[user_access_level]
                < access_levels_hierarchy[access_level]
            ):
                raise GraphQLError(f"Accès insuffisant au champ '{field_name}'")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def mask_sensitive_fields(
    data: Dict[str, Any],
    user: "AbstractUser",
    model_class: type,
    instance: models.Model = None,
) -> Dict[str, Any]:
    """
    Masque les champs sensibles dans un dictionnaire de données.

    Args:
        data: Données à masquer
        user: Utilisateur
        model_class: Classe du modèle
        instance: Instance du modèle

    Returns:
        Données avec champs masqués
    """
    if not user or not user.is_authenticated:
        return {}

    result = data.copy()

    for field_name, value in data.items():
        context = FieldContext(
            user=user,
            instance=instance,
            field_name=field_name,
            operation_type="read",
            model_class=model_class,
        )

        visibility, mask_value = field_permission_manager.get_field_visibility(context)

        if visibility == FieldVisibility.HIDDEN:
            result.pop(field_name, None)
        elif visibility == FieldVisibility.MASKED:
            result[field_name] = mask_value
        elif visibility == FieldVisibility.REDACTED and value:
            # Censurer partiellement (garder les premiers et derniers caractères)
            if isinstance(value, str) and len(value) > 4:
                result[field_name] = value[:2] + "*" * (len(value) - 4) + value[-2:]
            else:
                result[field_name] = "****"

    return result


# Instance globale du gestionnaire de permissions de champs
field_permission_manager = FieldPermissionManager()
