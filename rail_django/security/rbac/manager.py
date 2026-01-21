"""
RoleManager - Central class for role-based access control.

This module provides the RoleManager class that orchestrates all RBAC
functionality including role management, permission evaluation, and caching.
"""

import logging
from typing import TYPE_CHECKING, Callable, Optional, Union

from django.core.cache import cache
from django.db import models

from rail_django.config_proxy import get_setting

from .evaluation import PermissionEvaluationMixin
from .types import PermissionContext, RoleDefinition, RoleType

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser, Group

logger = logging.getLogger(__name__)


def _get_group_model():
    """Lazy import to avoid AppRegistryNotReady during Django setup."""
    from django.contrib.auth.models import Group

    return Group


class RoleManager(PermissionEvaluationMixin):
    """
    Central manager for role-based access control.

    Provides role registration/retrieval, permission evaluation with caching,
    policy engine integration, and role assignment via Django groups.
    """

    def __init__(self):
        """Initialize the role manager with default configuration and system roles."""
        self._roles_cache: dict[str, RoleDefinition] = {}
        self._permissions_cache: dict = {}
        self._role_hierarchy: dict[str, list[str]] = {}
        self._model_roles_registry: set[str] = set()
        self._owner_resolvers: dict[str, Callable[[PermissionContext], bool]] = {}
        self._assignment_resolvers: dict[str, Callable[[PermissionContext], bool]] = {}
        self._context_resolver_version = 1

        # Cache configuration
        self._permission_cache_enabled = bool(
            get_setting("security_settings.enable_permission_cache", True)
        )
        self._permission_cache_ttl = int(
            get_setting("security_settings.permission_cache_ttl_seconds", 300)
        )
        self._permission_cache_prefix = "rail:rbac:perm"
        self._permission_cache_version_prefix = "rail:rbac:ver"

        # Policy engine configuration
        self._policy_engine_enabled = bool(
            get_setting("security_settings.enable_policy_engine", True)
        )

        # Audit configuration
        self._permission_audit_enabled = bool(
            get_setting("security_settings.enable_permission_audit", False)
        )
        self._permission_audit_log_all = bool(
            get_setting("security_settings.permission_audit_log_all", False)
        )
        self._permission_audit_log_denies = bool(
            get_setting("security_settings.permission_audit_log_denies", True)
        )

        # Predefined system roles
        self.system_roles: dict[str, RoleDefinition] = {
            "superadmin": RoleDefinition(
                name="superadmin",
                description="Super administrateur avec tous les droits",
                role_type=RoleType.SYSTEM,
                permissions=["*"],
                is_system_role=True,
                max_users=5,
            ),
            "admin": RoleDefinition(
                name="admin",
                description="Administrateur systeme",
                role_type=RoleType.SYSTEM,
                permissions=[
                    "user.create", "user.read", "user.update", "user.delete",
                    "role.create", "role.read", "role.update", "role.delete",
                    "system.configure", "audit.read",
                ],
                is_system_role=True,
                max_users=10,
            ),
            "manager": RoleDefinition(
                name="manager",
                description="Gestionnaire metier",
                role_type=RoleType.BUSINESS,
                permissions=[
                    "user.read", "user.update",
                    "project.create", "project.read", "project.update", "project.delete",
                    "report.read", "report.create",
                ],
            ),
            "employee": RoleDefinition(
                name="employee",
                description="Employe standard",
                role_type=RoleType.BUSINESS,
                permissions=[
                    "user.read_own", "user.update_own",
                    "project.read", "project.update_assigned",
                    "task.create", "task.read", "task.update_own",
                ],
            ),
            "viewer": RoleDefinition(
                name="viewer",
                description="Utilisateur en lecture seule",
                role_type=RoleType.FUNCTIONAL,
                permissions=["user.read_own", "project.read_assigned", "task.read_assigned"],
            ),
        }

    # --- Role Registration ---

    def register_role(self, role_definition: RoleDefinition) -> None:
        """Register a new role definition. Skips if role already exists."""
        if (
            role_definition.name in self.system_roles
            or role_definition.name in self._roles_cache
        ):
            logger.debug("Le role '%s' est deja enregistre", role_definition.name)
            return
        self._roles_cache[role_definition.name] = role_definition
        if role_definition.parent_roles:
            self._role_hierarchy[role_definition.name] = role_definition.parent_roles
        logger.info(f"Role '{role_definition.name}' enregistre")

    def register_default_model_roles(self, model_class: type[models.Model]) -> None:
        """Create default CRUD roles (viewer, editor, manager) for a Django model."""
        if not model_class or model_class._meta.abstract or model_class._meta.auto_created:
            return
        model_label = model_class._meta.label_lower
        if model_label in self._model_roles_registry:
            return

        app_label = model_class._meta.app_label
        model_name = model_class._meta.model_name
        base_role_name = model_label.replace(".", "_")

        permissions = {
            "view": f"{app_label}.view_{model_name}",
            "add": f"{app_label}.add_{model_name}",
            "change": f"{app_label}.change_{model_name}",
            "delete": f"{app_label}.delete_{model_name}",
        }

        default_roles = [
            RoleDefinition(
                name=f"{base_role_name}_viewer",
                description=f"Lecture du modele {model_label}",
                role_type=RoleType.BUSINESS,
                permissions=[permissions["view"]],
            ),
            RoleDefinition(
                name=f"{base_role_name}_editor",
                description=f"Gestion de base du modele {model_label}",
                role_type=RoleType.BUSINESS,
                permissions=[permissions["view"], permissions["add"], permissions["change"]],
            ),
            RoleDefinition(
                name=f"{base_role_name}_manager",
                description=f"Administration complete du modele {model_label}",
                role_type=RoleType.BUSINESS,
                permissions=[permissions["view"], permissions["add"], permissions["change"], permissions["delete"]],
            ),
        ]
        for role_def in default_roles:
            self.register_role(role_def)
        self._model_roles_registry.add(model_label)

    def get_role_definition(self, role_name: str) -> Optional[RoleDefinition]:
        """Get the definition of a role by name."""
        if role_name in self.system_roles:
            return self.system_roles[role_name]
        return self._roles_cache.get(role_name)

    # --- User Role Management ---

    def get_user_roles(self, user: "AbstractUser") -> list[str]:
        """Get role names assigned to a user from Django groups and system flags."""
        if not user or not getattr(user, "is_authenticated", False):
            return []
        if getattr(user, "pk", None) is None:
            return []
        roles = list(user.groups.values_list("name", flat=True))
        if user.is_superuser:
            roles.append("superadmin")
        elif user.is_staff:
            roles.append("admin")
        return roles

    def get_effective_permissions(
        self, user: "AbstractUser", context: PermissionContext = None
    ) -> set[str]:
        """Get all effective permissions for a user (roles + inherited + Django perms)."""
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
                parent_permissions = self._get_inherited_permissions(role_name)
                permissions.update(parent_permissions)

        django_permissions = user.get_all_permissions()
        permissions.update(django_permissions)
        return permissions

    def _get_inherited_permissions(
        self, role_name: str, visited: Optional[set[str]] = None
    ) -> set[str]:
        """Get permissions inherited from parent roles."""
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
                    permissions.update(self._get_inherited_permissions(parent_role, visited))
        return permissions

    def _permission_in_effective_permissions(
        self, permission: str, effective_permissions: set[str]
    ) -> bool:
        """Check if a permission matches the effective permissions (supports wildcards)."""
        if permission in effective_permissions:
            return True
        if "*" in effective_permissions:
            return True
        for perm in effective_permissions:
            if perm.endswith("*"):
                prefix = perm[:-1]
                if permission.startswith(prefix):
                    return True
        return False

    def assign_role_to_user(self, user: "AbstractUser", role_name: str) -> None:
        """Assign a role to a user via Django groups."""
        role_def = self.get_role_definition(role_name)
        if not role_def:
            raise ValueError(f"Role '{role_name}' non trouve")

        group_model = _get_group_model()
        group, created = group_model.objects.get_or_create(name=role_name)

        if role_def.max_users:
            current_count = group.user_set.count()
            if current_count >= role_def.max_users and not group.user_set.filter(id=user.id).exists():
                raise ValueError(f"Limite d'utilisateurs atteinte pour le role '{role_name}'")

        user.groups.add(group)
        self.invalidate_user_cache(user)
        logger.info(f"Role '{role_name}' assigne a l'utilisateur {user.username}")

    def remove_role_from_user(self, user: "AbstractUser", role_name: str) -> None:
        """Remove a role from a user."""
        group_model = _get_group_model()
        try:
            group = group_model.objects.get(name=role_name)
            user.groups.remove(group)
            self.invalidate_user_cache(user)
            logger.info(f"Role '{role_name}' retire de l'utilisateur {user.username}")
        except group_model.DoesNotExist:
            logger.warning(f"Groupe '{role_name}' non trouve")

    # --- Permission Caching ---

    def _get_cache_version(self, user_id: Optional[int]) -> int:
        """Get the current cache version for a user."""
        if not user_id:
            return 0
        cache_key = f"{self._permission_cache_version_prefix}:{user_id}"
        version = cache.get(cache_key)
        if version is None:
            cache.set(cache_key, 1)
            return 1
        try:
            return int(version)
        except (TypeError, ValueError):
            return 1

    def bump_user_cache_version(self, user_id: Optional[int]) -> None:
        """Increment the cache version for a user, invalidating cached permissions."""
        if not user_id:
            return
        cache_key = f"{self._permission_cache_version_prefix}:{user_id}"
        try:
            cache.incr(cache_key)
        except Exception:
            current = cache.get(cache_key) or 0
            cache.set(cache_key, int(current) + 1)

    def invalidate_user_cache(self, user: "AbstractUser") -> None:
        """Invalidate all cached permissions for a user."""
        user_id = getattr(user, "id", None)
        self.bump_user_cache_version(user_id)

    def _build_permission_cache_key(
        self, user_id: Optional[int], permission: str, context: Optional[PermissionContext]
    ) -> Optional[str]:
        """Build a cache key for a permission check."""
        if not self._permission_cache_enabled or not user_id:
            return None
        from ..policies import policy_manager

        version = self._get_cache_version(user_id)
        policy_version = policy_manager.get_version()
        resolver_version = self._context_resolver_version

        model_label = ""
        object_id = ""
        operation = ""
        if context is not None:
            model_class = context.model_class
            if model_class is None and context.object_instance is not None:
                model_class = context.object_instance.__class__
            if model_class is not None:
                model_label = self._normalize_model_key(model_class)
            object_id = str(context.object_id or getattr(context.object_instance, "pk", "") or "")
            operation = str(context.operation or "")
            is_contextual = permission.endswith("_own") or permission.endswith("_assigned")
            if is_contextual and not object_id:
                return None

        return (
            f"{self._permission_cache_prefix}:{user_id}:{version}:{policy_version}:"
            f"{permission}:{model_label}:{object_id}:{operation}:{resolver_version}"
        )

    def _get_cached_permission(self, cache_key: Optional[str]) -> Optional[bool]:
        """Retrieve a cached permission decision."""
        if not cache_key:
            return None
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and "allowed" in cached:
            return bool(cached["allowed"])
        return None

    def _set_cached_permission(self, cache_key: Optional[str], allowed: bool) -> None:
        """Store a permission decision in the cache."""
        if not cache_key or not self._permission_cache_ttl:
            return
        cache.set(cache_key, {"allowed": bool(allowed)}, timeout=self._permission_cache_ttl)


# Global singleton instance
role_manager = RoleManager()

# Register system roles
for _role_name, _role_def in role_manager.system_roles.items():
    role_manager.register_role(_role_def)

__all__ = ["RoleManager", "role_manager"]
