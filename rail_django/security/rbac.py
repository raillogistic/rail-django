"""
Système de contrôle d'accès basé sur les rôles (RBAC) pour Django GraphQL.

Ce module fournit :
- Gestion des rôles et permissions
- Hiérarchie des rôles
- Permissions contextuelles
- Intégration avec Django Groups
"""

import logging
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Type, Union

from django.db import models
from graphql import GraphQLError

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser, Group


def _get_group_model():
    """Lazy import to avoid AppRegistryNotReady during Django setup."""
    from django.contrib.auth.models import Group

    return Group

logger = logging.getLogger(__name__)


class RoleType(Enum):
    """Types de rôles dans le système."""
    SYSTEM = "system"  # Rôles système (admin, superuser)
    BUSINESS = "business"  # Rôles métier (manager, employee)
    FUNCTIONAL = "functional"  # Rôles fonctionnels (editor, viewer)


class PermissionScope(Enum):
    """Portée des permissions."""
    GLOBAL = "global"  # Permission globale
    ORGANIZATION = "organization"  # Permission au niveau organisation
    DEPARTMENT = "department"  # Permission au niveau département
    PROJECT = "project"  # Permission au niveau projet
    OBJECT = "object"  # Permission au niveau objet


@dataclass
class RoleDefinition:
    """Définition d'un rôle."""
    name: str
    description: str
    role_type: RoleType
    permissions: List[str]
    parent_roles: List[str] = None
    is_system_role: bool = False
    max_users: Optional[int] = None


@dataclass
class PermissionContext:
    """Contexte d'une permission."""
    user: "AbstractUser"
    object_id: Optional[str] = None
    object_instance: Optional[models.Model] = None
    model_class: Optional[Type[models.Model]] = None
    organization_id: Optional[str] = None
    department_id: Optional[str] = None
    project_id: Optional[str] = None
    additional_context: Dict[str, Any] = None


class RoleManager:
    """
    Gestionnaire des rôles et permissions.
    """

    def __init__(self):
        """Initialise le gestionnaire de rôles."""
        self._roles_cache = {}
        self._permissions_cache = {}
        self._role_hierarchy = {}
        self._model_roles_registry: Set[str] = set()

        # Rôles système prédéfinis
        self.system_roles = {
            'superadmin': RoleDefinition(
                name='superadmin',
                description='Super administrateur avec tous les droits',
                role_type=RoleType.SYSTEM,
                permissions=['*'],
                is_system_role=True,
                max_users=5
            ),
            'admin': RoleDefinition(
                name='admin',
                description='Administrateur système',
                role_type=RoleType.SYSTEM,
                permissions=[
                    'user.create', 'user.read', 'user.update', 'user.delete',
                    'role.create', 'role.read', 'role.update', 'role.delete',
                    'system.configure', 'audit.read'
                ],
                is_system_role=True,
                max_users=10
            ),
            'manager': RoleDefinition(
                name='manager',
                description='Gestionnaire métier',
                role_type=RoleType.BUSINESS,
                permissions=[
                    'user.read', 'user.update',
                    'project.create', 'project.read', 'project.update', 'project.delete',
                    'report.read', 'report.create'
                ]
            ),
            'employee': RoleDefinition(
                name='employee',
                description='Employé standard',
                role_type=RoleType.BUSINESS,
                permissions=[
                    'user.read_own', 'user.update_own',
                    'project.read', 'project.update_assigned',
                    'task.create', 'task.read', 'task.update_own'
                ]
            ),
            'viewer': RoleDefinition(
                name='viewer',
                description='Utilisateur en lecture seule',
                role_type=RoleType.FUNCTIONAL,
                permissions=[
                    'user.read_own',
                    'project.read_assigned',
                    'task.read_assigned'
                ]
            )
        }

    def register_role(self, role_definition: RoleDefinition):
        """
        Enregistre une nouvelle définition de rôle.

        Args:
            role_definition: Définition du rôle à enregistrer
        """
        if role_definition.name in self.system_roles or role_definition.name in self._roles_cache:
            logger.debug("Le rôle '%s' est déjà enregistré", role_definition.name)
            return
        self._roles_cache[role_definition.name] = role_definition

        # Construire la hiérarchie
        if role_definition.parent_roles:
            self._role_hierarchy[role_definition.name] = role_definition.parent_roles

        logger.info(f"Rôle '{role_definition.name}' enregistré")

    def register_default_model_roles(self, model_class: Type[models.Model]):
        """Crée des rôles CRUD par défaut pour un modèle installé."""

        if not model_class or model_class._meta.abstract or model_class._meta.auto_created:
            return

        model_label = model_class._meta.label_lower
        if model_label in self._model_roles_registry:
            return

        app_label = model_class._meta.app_label
        model_name = model_class._meta.model_name
        base_role_name = model_label.replace('.', '_')

        permissions = {
            'view': f"{app_label}.view_{model_name}",
            'add': f"{app_label}.add_{model_name}",
            'change': f"{app_label}.change_{model_name}",
            'delete': f"{app_label}.delete_{model_name}",
        }

        default_roles = [
            RoleDefinition(
                name=f"{base_role_name}_viewer",
                description=f"Lecture du modèle {model_label}",
                role_type=RoleType.BUSINESS,
                permissions=[permissions['view']],
            ),
            RoleDefinition(
                name=f"{base_role_name}_editor",
                description=f"Gestion de base du modèle {model_label}",
                role_type=RoleType.BUSINESS,
                permissions=[permissions['view'], permissions['add'], permissions['change']],
            ),
            RoleDefinition(
                name=f"{base_role_name}_manager",
                description=f"Administration complète du modèle {model_label}",
                role_type=RoleType.BUSINESS,
                permissions=[
                    permissions['view'],
                    permissions['add'],
                    permissions['change'],
                    permissions['delete'],
                ],
            ),
        ]

        for role_def in default_roles:
            self.register_role(role_def)

        self._model_roles_registry.add(model_label)

    def get_role_definition(self, role_name: str) -> Optional[RoleDefinition]:
        """
        Récupère la définition d'un rôle.

        Args:
            role_name: Nom du rôle

        Returns:
            Définition du rôle ou None
        """
        # Vérifier d'abord les rôles système
        if role_name in self.system_roles:
            return self.system_roles[role_name]

        return self._roles_cache.get(role_name)

    def get_user_roles(self, user: "AbstractUser") -> List[str]:
        """
        Récupère les rôles d'un utilisateur.

        Args:
            user: Utilisateur

        Returns:
            Liste des noms de rôles
        """
        if not user or not getattr(user, "is_authenticated", False):
            return []
        if getattr(user, "pk", None) is None:
            return []

        # Retrieve roles directly from Django groups
        roles = list(user.groups.values_list("name", flat=True))

        # Add system roles if applicable
        if user.is_superuser:
            roles.append('superadmin')
        elif user.is_staff:
            roles.append('admin')

        return roles

    def get_effective_permissions(self, user: "AbstractUser",
                                  context: PermissionContext = None) -> Set[str]:
        """
        Récupère les permissions effectives d'un utilisateur.

        Args:
            user: Utilisateur
            context: Contexte de la permission

        Returns:
            Ensemble des permissions effectives
        """
        if not user or not getattr(user, "is_authenticated", False):
            return set()
        if getattr(user, "pk", None) is None:
            return set()

        permissions = set()
        user_roles = self.get_user_roles(user)

        for role_name in user_roles:
            role_def = self.get_role_definition(role_name)
            if role_def:
                permissions.update(role_def.permissions)

                # Add parent role permissions
                parent_permissions = self._get_inherited_permissions(role_name)
                permissions.update(parent_permissions)

        # Native Django permissions
        django_permissions = user.get_all_permissions()
        permissions.update(django_permissions)

        return permissions

    def _get_inherited_permissions(self, role_name: str,
                                   visited: Optional[Set[str]] = None) -> Set[str]:
        """
        Récupère les permissions héritées des rôles parents.

        Args:
            role_name: Nom du rôle

        Returns:
            Ensemble des permissions héritées
        """
        permissions = set()
        if visited is None:
            visited = set()
        if role_name in visited:
            logger.warning("Cycle detected in role hierarchy: %s", role_name)
            return permissions
        visited.add(role_name)

        if role_name in self._role_hierarchy:
            for parent_role in self._role_hierarchy[role_name]:
                parent_def = self.get_role_definition(parent_role)
                if parent_def:
                    permissions.update(parent_def.permissions)
                    # Récursion pour les rôles grands-parents
                    permissions.update(
                        self._get_inherited_permissions(parent_role, visited)
                    )

        return permissions

    def _permission_in_effective_permissions(self, permission: str,
                                             effective_permissions: Set[str]) -> bool:
        if permission in effective_permissions:
            return True
        if '*' in effective_permissions:
            return True
        for perm in effective_permissions:
            if perm.endswith('*'):
                prefix = perm[:-1]
                if permission.startswith(prefix):
                    return True
        return False

    def has_permission(self, user: "AbstractUser", permission: str,
                       context: PermissionContext = None) -> bool:
        """
        Vérifie si un utilisateur a une permission spécifique.

        Args:
            user: Utilisateur
            permission: Permission à vérifier
            context: Contexte de la permission

        Returns:
            True si l'utilisateur a la permission
        """
        if not user or not user.is_authenticated:
            return False

        # Super utilisateur a toutes les permissions
        if user.is_superuser:
            return True

        effective_permissions = self.get_effective_permissions(user, context)

        is_contextual = permission.endswith('_own') or permission.endswith('_assigned')
        if is_contextual:
            if not context:
                return False
            if not self._permission_in_effective_permissions(
                permission, effective_permissions
            ):
                return False
            return self._check_contextual_permission(user, permission, context)

        if self._permission_in_effective_permissions(
            permission, effective_permissions
        ):
            return True

        # Vérifier les permissions contextuelles
        if context:
            return self._check_contextual_permission(user, permission, context)

        return False

    def _check_contextual_permission(self, user: "AbstractUser",
                                     permission: str, context: PermissionContext) -> bool:
        """
        Vérifie les permissions contextuelles.

        Args:
            user: Utilisateur
            permission: Permission à vérifier
            context: Contexte de la permission

        Returns:
            True si l'utilisateur a la permission dans ce contexte
        """
        # Permissions sur ses propres objets
        if permission.endswith('_own'):
            return self._is_object_owner(context)

        # Permissions sur les objets assignés
        if permission.endswith('_assigned'):
            return self._is_object_assigned(context)

        return False

    def _get_context_instance(self, context: PermissionContext) -> Optional[models.Model]:
        if context.object_instance is not None:
            return context.object_instance
        if context.model_class is None or context.object_id is None:
            return None
        try:
            return context.model_class.objects.get(pk=context.object_id)
        except context.model_class.DoesNotExist:
            return None
        except Exception as e:
            logger.error("Error retrieving object: %s", e)
            return None

    def _is_object_owner(self, context: PermissionContext) -> bool:
        """
        Vérifie si l'utilisateur est propriétaire de l'objet.

        Args:
            context: Contexte de la permission

        Returns:
            True si l'utilisateur est propriétaire
        """
        obj = self._get_context_instance(context)
        if obj is None:
            return False

        user = context.user
        for attr in ("owner", "created_by", "user"):
            if hasattr(obj, attr):
                value = getattr(obj, attr)
                if value == user:
                    return True
                if getattr(value, "pk", value) == getattr(user, "pk", user):
                    return True

        return False

    def _is_object_assigned(self, context: PermissionContext) -> bool:
        """
        Vérifie si l'objet est assigné à l'utilisateur.

        Args:
            context: Contexte de la permission

        Returns:
            True si l'objet est assigné à l'utilisateur
        """
        obj = self._get_context_instance(context)
        if obj is None:
            return False

        user = context.user
        if hasattr(obj, 'assigned_to'):
            assigned_to = obj.assigned_to
            if assigned_to == user:
                return True
            return getattr(assigned_to, "pk", assigned_to) == getattr(user, "pk", user)
        if hasattr(obj, 'assignees'):
            try:
                assignees = obj.assignees.all()
            except Exception:
                return False
            return user in assignees

        return False

    def assign_role_to_user(self, user: "AbstractUser", role_name: str):
        """
        Assigne un rôle à un utilisateur.

        Args:
            user: Utilisateur
            role_name: Nom du rôle à assigner
        """
        role_def = self.get_role_definition(role_name)
        if not role_def:
            raise ValueError(f"Rôle '{role_name}' non trouvé")

        # Vérifier les limites de rôle
        group_model = _get_group_model()
        group, created = group_model.objects.get_or_create(name=role_name)

        if role_def.max_users:
            current_count = group.user_set.count()
            if current_count >= role_def.max_users and not group.user_set.filter(id=user.id).exists():
                raise ValueError(f"Limite d'utilisateurs atteinte pour le rôle '{role_name}'")

        user.groups.add(group)

        # Cache removed: no invalidation needed

        logger.info(f"Rôle '{role_name}' assigné à l'utilisateur {user.username}")

    def remove_role_from_user(self, user: "AbstractUser", role_name: str):
        """
        Retire un rôle d'un utilisateur.

        Args:
            user: Utilisateur
            role_name: Nom du rôle à retirer
        """
        group_model = _get_group_model()

        try:
            group = group_model.objects.get(name=role_name)
            user.groups.remove(group)

            # Cache removed: no invalidation needed

            logger.info(f"Rôle '{role_name}' retiré de l'utilisateur {user.username}")
        except group_model.DoesNotExist:
            logger.warning(f"Groupe '{role_name}' non trouvé")


def require_role(required_roles: Union[str, List[str]]):
    """
    Décorateur pour exiger des rôles spécifiques.

    Args:
        required_roles: Rôle(s) requis

    Returns:
        Décorateur de vérification de rôle
    """
    if isinstance(required_roles, str):
        required_roles = [required_roles]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extraire l'utilisateur du contexte GraphQL
            info = None
            for arg in args:
                if hasattr(arg, 'context'):
                    info = arg
                    break

            if not info or not hasattr(info.context, 'user'):
                raise GraphQLError("Contexte utilisateur non disponible")

            user = info.context.user
            if not user or not user.is_authenticated:
                raise GraphQLError("Authentification requise")

            user_roles = role_manager.get_user_roles(user)

            # Vérifier si l'utilisateur a au moins un des rôles requis
            if not any(role in user_roles for role in required_roles):
                raise GraphQLError(f"Rôles requis: {', '.join(required_roles)}")

            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_permission(permission: str, context_func: callable = None):
    """
    Décorateur pour exiger une permission spécifique.

    Args:
        permission: Permission requise
        context_func: Fonction pour extraire le contexte

    Returns:
        Décorateur de vérification de permission
    """
    def _extract_object_instance(args, kwargs):
        for key in ("instance", "obj", "object"):
            if key in kwargs and kwargs[key] is not None:
                return kwargs[key]

        for arg in args:
            if hasattr(arg, "context"):
                continue
            if isinstance(arg, models.Model):
                return arg

        return None

    def _extract_object_id(kwargs):
        for key in ("object_id", "id", "pk"):
            if key in kwargs and kwargs[key] is not None:
                return kwargs[key]

        input_value = kwargs.get("input")
        if isinstance(input_value, dict):
            for key in ("object_id", "id", "pk"):
                if key in input_value and input_value[key] is not None:
                    return input_value[key]
        elif input_value is not None:
            for key in ("object_id", "id", "pk"):
                if hasattr(input_value, key):
                    value = getattr(input_value, key)
                    if value is not None:
                        return value

        return None

    def _infer_model_class(info):
        graphql_type = getattr(info, "return_type", None)
        graphene_type = getattr(graphql_type, "graphene_type", None)
        meta = getattr(graphene_type, "_meta", None)
        return getattr(meta, "model", None)

    def _normalize_permission_context(context, user, info, args, kwargs):
        if context is None:
            context = PermissionContext(user=user)
        elif isinstance(context, dict):
            known_keys = {
                "user",
                "object_instance",
                "instance",
                "object",
                "object_id",
                "id",
                "pk",
                "model_class",
                "organization_id",
                "department_id",
                "project_id",
                "additional_context",
            }
            extra = {key: value for key, value in context.items() if key not in known_keys}
            additional_context = context.get("additional_context") or extra or None
            context = PermissionContext(
                user=user,
                object_instance=(
                    context.get("object_instance")
                    or context.get("instance")
                    or context.get("object")
                ),
                object_id=(
                    context.get("object_id")
                    or context.get("id")
                    or context.get("pk")
                ),
                model_class=context.get("model_class"),
                organization_id=context.get("organization_id"),
                department_id=context.get("department_id"),
                project_id=context.get("project_id"),
                additional_context=additional_context,
            )
        elif not isinstance(context, PermissionContext):
            context = PermissionContext(
                user=user, additional_context={"value": context}
            )

        if context.user is None:
            context.user = user

        if context.object_instance is None:
            context.object_instance = _extract_object_instance(args, kwargs)

        if context.object_instance is not None and context.model_class is None:
            context.model_class = context.object_instance.__class__

        if context.object_id is None:
            context.object_id = _extract_object_id(kwargs)
            if context.object_id is None and context.object_instance is not None:
                context.object_id = getattr(context.object_instance, "pk", None)

        if context.model_class is None:
            context.model_class = _infer_model_class(info)

        return context

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extraire l'utilisateur du contexte GraphQL
            info = None
            for arg in args:
                if hasattr(arg, 'context'):
                    info = arg
                    break

            if not info or not hasattr(info.context, 'user'):
                raise GraphQLError("Contexte utilisateur non disponible")

            user = info.context.user
            if not user or not user.is_authenticated:
                raise GraphQLError("Authentification requise")

            # Construire le contexte si une fonction est fournie
            context = None
            if context_func:
                context = context_func(*args, **kwargs)
            context = _normalize_permission_context(context, user, info, args, kwargs)

            if not role_manager.has_permission(user, permission, context):
                raise GraphQLError(f"Permission requise: {permission}")

            return func(*args, **kwargs)
        return wrapper
    return decorator


# Instance globale du gestionnaire de rôles
role_manager = RoleManager()

# Enregistrer les rôles système
for role_name, role_def in role_manager.system_roles.items():
    role_manager.register_role(role_def)
