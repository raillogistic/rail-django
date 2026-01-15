"""
Système de contrôle d'accès basé sur les rôles (RBAC) pour Django GraphQL.

Ce module fournit :
- Gestion des rôles et permissions
- Hiérarchie des rôles
- Permissions contextuelles
- Intégration avec Django Groups
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

from django.core.cache import cache
from django.db import models
from graphql import GraphQLError

from rail_django.config_proxy import get_setting

from .policies import PolicyContext as AccessPolicyContext
from .policies import PolicyEffect, policy_manager

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
    permissions: list[str]
    parent_roles: list[str] = None
    is_system_role: bool = False
    max_users: Optional[int] = None


@dataclass
class PermissionContext:
    """Contexte d'une permission."""
    user: "AbstractUser"
    object_id: Optional[str] = None
    object_instance: Optional[models.Model] = None
    model_class: Optional[type[models.Model]] = None
    operation: Optional[str] = None
    organization_id: Optional[str] = None
    department_id: Optional[str] = None
    project_id: Optional[str] = None
    additional_context: dict[str, Any] = None


@dataclass
class PolicyDecisionDetail:
    name: str
    effect: str
    priority: int
    reason: Optional[str] = None


@dataclass
class PermissionExplanation:
    permission: str
    allowed: bool
    reason: Optional[str] = None
    policy_decision: Optional[PolicyDecisionDetail] = None
    policy_matches: list[PolicyDecisionDetail] = field(default_factory=list)
    user_roles: list[str] = field(default_factory=list)
    effective_permissions: set[str] = field(default_factory=set)
    context_required: bool = False
    context_allowed: Optional[bool] = None
    context_reason: Optional[str] = None


class RoleManager:
    """
    Gestionnaire des rôles et permissions.
    """

    def __init__(self):
        """Initialise le gestionnaire de rôles."""
        self._roles_cache = {}
        self._permissions_cache = {}
        self._role_hierarchy = {}
        self._model_roles_registry: set[str] = set()
        self._owner_resolvers: dict[str, Callable[[PermissionContext], bool]] = {}
        self._assignment_resolvers: dict[str, Callable[[PermissionContext], bool]] = {}
        self._context_resolver_version = 1

        self._permission_cache_enabled = bool(
            get_setting("security_settings.enable_permission_cache", True)
        )
        self._permission_cache_ttl = int(
            get_setting("security_settings.permission_cache_ttl_seconds", 300)
        )
        self._permission_cache_prefix = "rail:rbac:perm"
        self._permission_cache_version_prefix = "rail:rbac:ver"
        self._policy_engine_enabled = bool(
            get_setting("security_settings.enable_policy_engine", True)
        )
        self._permission_audit_enabled = bool(
            get_setting("security_settings.enable_permission_audit", False)
        )
        self._permission_audit_log_all = bool(
            get_setting("security_settings.permission_audit_log_all", False)
        )
        self._permission_audit_log_denies = bool(
            get_setting("security_settings.permission_audit_log_denies", True)
        )

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

    def register_default_model_roles(self, model_class: type[models.Model]):
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

    def register_owner_resolver(
        self,
        model_class: Union[type[models.Model], str],
        resolver: Callable[[PermissionContext], bool],
    ) -> None:
        key = self._normalize_model_key(model_class)
        if not key:
            return
        self._owner_resolvers[key] = resolver
        self._context_resolver_version += 1

    def register_assignment_resolver(
        self,
        model_class: Union[type[models.Model], str],
        resolver: Callable[[PermissionContext], bool],
    ) -> None:
        key = self._normalize_model_key(model_class)
        if not key:
            return
        self._assignment_resolvers[key] = resolver
        self._context_resolver_version += 1

    def _normalize_model_key(self, model_class: Union[type[models.Model], str, None]) -> str:
        if model_class is None:
            return ""
        if isinstance(model_class, str):
            return model_class.lower()
        meta = getattr(model_class, "_meta", None)
        label_lower = getattr(meta, "label_lower", None)
        if label_lower:
            return label_lower
        name = getattr(model_class, "__name__", None)
        return name.lower() if name else ""

    def _get_model_key_from_context(self, context: PermissionContext) -> str:
        if context.model_class is not None:
            return self._normalize_model_key(context.model_class)
        if context.object_instance is not None:
            return self._normalize_model_key(context.object_instance.__class__)
        return ""

    def _apply_context_resolver(
        self,
        resolver: Optional[Callable[[PermissionContext], bool]],
        context: PermissionContext,
        obj: Optional[models.Model],
    ) -> Optional[bool]:
        if resolver is None:
            return None
        try:
            return bool(resolver(context))
        except TypeError:
            try:
                return bool(resolver(context.user))
            except TypeError:
                try:
                    return bool(resolver(context.user, obj))
                except TypeError:
                    return bool(resolver(context.user, obj, context))
        except Exception as exc:
            logger.warning("Resolver error for context %s: %s", context, exc)
            return False

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

    def get_user_roles(self, user: "AbstractUser") -> list[str]:
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
                                  context: PermissionContext = None) -> set[str]:
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
                                   visited: Optional[set[str]] = None) -> set[str]:
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
                                             effective_permissions: set[str]) -> bool:
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

    def _get_cache_version(self, user_id: Optional[int]) -> int:
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
        if not user_id:
            return
        cache_key = f"{self._permission_cache_version_prefix}:{user_id}"
        try:
            cache.incr(cache_key)
        except Exception:
            current = cache.get(cache_key) or 0
            cache.set(cache_key, int(current) + 1)

    def invalidate_user_cache(self, user: "AbstractUser") -> None:
        user_id = getattr(user, "id", None)
        self.bump_user_cache_version(user_id)

    def _build_permission_cache_key(
        self,
        user_id: Optional[int],
        permission: str,
        context: Optional[PermissionContext],
    ) -> Optional[str]:
        if not self._permission_cache_enabled or not user_id:
            return None
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
            object_id = str(
                context.object_id
                or getattr(context.object_instance, "pk", "")
                or ""
            )
            operation = str(context.operation or "")
            is_contextual = permission.endswith("_own") or permission.endswith(
                "_assigned"
            )
            if is_contextual and not object_id:
                return None
        return (
            f"{self._permission_cache_prefix}:{user_id}:{version}:{policy_version}:"
            f"{permission}:{model_label}:{object_id}:{operation}:{resolver_version}"
        )

    def _get_cached_permission(self, cache_key: Optional[str]) -> Optional[bool]:
        if not cache_key:
            return None
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and "allowed" in cached:
            return bool(cached["allowed"])
        return None

    def _set_cached_permission(self, cache_key: Optional[str], allowed: bool) -> None:
        if not cache_key or not self._permission_cache_ttl:
            return
        cache.set(cache_key, {"allowed": bool(allowed)}, timeout=self._permission_cache_ttl)

    def _build_policy_context(
        self,
        user: "AbstractUser",
        permission: str,
        context: Optional[PermissionContext],
    ) -> AccessPolicyContext:
        model_class = None
        object_instance = None
        object_id = None
        operation = None
        additional_context = None
        request = None
        if context is not None:
            model_class = context.model_class
            object_instance = context.object_instance
            object_id = context.object_id
            operation = context.operation
            additional_context = context.additional_context
            if isinstance(additional_context, dict):
                request = additional_context.get("request") or additional_context.get(
                    "context"
                )
        return AccessPolicyContext(
            user=user,
            permission=permission,
            model_class=model_class,
            object_instance=object_instance,
            object_id=object_id,
            operation=operation,
            additional_context=additional_context,
            request=request,
        )

    def _describe_policy(self, policy: Any) -> PolicyDecisionDetail:
        return PolicyDecisionDetail(
            name=str(getattr(policy, "name", "")),
            effect=str(getattr(getattr(policy, "effect", None), "value", None) or getattr(policy, "effect", "")),
            priority=int(getattr(policy, "priority", 0) or 0),
            reason=getattr(policy, "reason", None),
        )

    def has_permission(
        self,
        user: "AbstractUser",
        permission: str,
        context: PermissionContext = None,
    ) -> bool:
        audit_enabled = (
            self._permission_audit_enabled
            and (self._permission_audit_log_all or self._permission_audit_log_denies)
        )
        cache_key = self._build_permission_cache_key(
            getattr(user, "id", None), permission, context
        )
        if cache_key and not audit_enabled:
            cached = self._get_cached_permission(cache_key)
            if cached is not None:
                return cached

        allowed, explanation = self._evaluate_permission(
            user, permission, context, include_explanation=audit_enabled
        )

        if cache_key:
            self._set_cached_permission(cache_key, allowed)

        if audit_enabled and (
            self._permission_audit_log_all
            or (self._permission_audit_log_denies and not allowed)
        ):
            self._audit_permission_decision(
                user, permission, context, explanation
            )

        return allowed

    def _check_contextual_permission_with_reason(
        self, permission: str, context: PermissionContext
    ) -> tuple[bool, Optional[str]]:
        if permission.endswith("_own"):
            allowed = self._is_object_owner(context)
            return allowed, None if allowed else "not_owner"
        if permission.endswith("_assigned"):
            allowed = self._is_object_assigned(context)
            return allowed, None if allowed else "not_assigned"
        return False, "context_not_applicable"

    def _evaluate_permission(
        self,
        user: "AbstractUser",
        permission: str,
        context: Optional[PermissionContext],
        *,
        include_explanation: bool = False,
    ) -> tuple[bool, Optional[PermissionExplanation]]:
        explanation = None
        if include_explanation:
            explanation = PermissionExplanation(
                permission=permission, allowed=False
            )

        if not user or not getattr(user, "is_authenticated", False):
            if explanation:
                explanation.reason = "authentication_required"
            return False, explanation

        if self._policy_engine_enabled:
            policy_context = self._build_policy_context(user, permission, context)
            if include_explanation:
                policy_explanation = policy_manager.explain(policy_context)
                if policy_explanation and policy_explanation.decision:
                    decision = policy_explanation.decision
                    if explanation:
                        explanation.policy_decision = self._describe_policy(
                            decision.policy
                        )
                        explanation.policy_matches = [
                            self._describe_policy(match)
                            for match in policy_explanation.matches
                        ]
                        explanation.allowed = decision.allowed
                        explanation.reason = (
                            decision.reason
                            or (
                                "policy_allow"
                                if decision.effect == PolicyEffect.ALLOW
                                else "policy_deny"
                            )
                        )
                    return decision.allowed, explanation
            else:
                decision = policy_manager.evaluate(policy_context)
                if decision is not None:
                    return decision.allowed, None

        if user.is_superuser:
            if explanation:
                explanation.allowed = True
                explanation.reason = "superuser"
            return True, explanation

        effective_permissions = self.get_effective_permissions(user, context)
        user_roles = self.get_user_roles(user)

        if explanation:
            explanation.user_roles = list(user_roles)
            explanation.effective_permissions = set(effective_permissions)

        is_contextual = permission.endswith("_own") or permission.endswith("_assigned")
        if is_contextual:
            if explanation:
                explanation.context_required = True
            if not context:
                if explanation:
                    explanation.reason = "context_required"
                return False, explanation
            if not self._permission_in_effective_permissions(
                permission, effective_permissions
            ):
                if explanation:
                    explanation.reason = "permission_missing"
                return False, explanation
            allowed, reason = self._check_contextual_permission_with_reason(
                permission, context
            )
            if explanation:
                explanation.allowed = allowed
                explanation.context_allowed = allowed
                explanation.context_reason = reason
                explanation.reason = reason or "context_allowed"
            return allowed, explanation

        if self._permission_in_effective_permissions(
            permission, effective_permissions
        ):
            if explanation:
                explanation.allowed = True
                explanation.reason = "permission_granted"
            return True, explanation

        if context:
            allowed, reason = self._check_contextual_permission_with_reason(
                permission, context
            )
            if explanation:
                explanation.allowed = allowed
                explanation.context_allowed = allowed
                explanation.context_reason = reason
                explanation.reason = reason or "context_allowed"
            return allowed, explanation

        if explanation:
            explanation.reason = "permission_missing"
        return False, explanation

    def _audit_permission_decision(
        self,
        user: "AbstractUser",
        permission: str,
        context: Optional[PermissionContext],
        explanation: Optional[PermissionExplanation],
    ) -> None:
        if explanation is None:
            return
        try:
            from ..extensions.audit import AuditEventType, log_audit_event
        except Exception:
            return

        request = None
        if context and isinstance(context.additional_context, dict):
            request = context.additional_context.get("request") or context.additional_context.get("context")

        model_label = ""
        object_id = ""
        operation = None
        if context:
            model_class = context.model_class
            if model_class is None and context.object_instance is not None:
                model_class = context.object_instance.__class__
            if model_class is not None:
                model_label = self._normalize_model_key(model_class)
            object_id = str(
                context.object_id
                or getattr(context.object_instance, "pk", "")
                or ""
            )
            operation = context.operation

        additional_data = {
            "permission": permission,
            "allowed": explanation.allowed,
            "reason": explanation.reason,
            "model": model_label,
            "object_id": object_id,
            "operation": operation,
            "roles": explanation.user_roles,
        }

        if explanation.policy_decision:
            additional_data["policy"] = {
                "name": explanation.policy_decision.name,
                "effect": explanation.policy_decision.effect,
                "priority": explanation.policy_decision.priority,
                "reason": explanation.policy_decision.reason,
            }

        log_audit_event(
            request,
            AuditEventType.DATA_ACCESS,
            user=user,
            success=bool(explanation.allowed),
            additional_data=additional_data,
        )

    def explain_permission(
        self, user: "AbstractUser", permission: str, context: PermissionContext = None
    ) -> PermissionExplanation:
        allowed, explanation = self._evaluate_permission(
            user, permission, context, include_explanation=True
        )
        if explanation is None:
            explanation = PermissionExplanation(
                permission=permission, allowed=allowed
            )
        return explanation

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
        allowed, _ = self._check_contextual_permission_with_reason(
            permission, context
        )
        return allowed

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

        model_key = self._get_model_key_from_context(context)
        resolver = self._owner_resolvers.get(model_key) if model_key else None

        if resolver is None:
            for attr in ("is_owner", "is_owned_by", "owned_by"):
                candidate = getattr(obj, attr, None)
                if callable(candidate):
                    resolver = candidate
                    break

        if resolver is not None:
            resolved = self._apply_context_resolver(resolver, context, obj)
            if resolved is not None:
                return bool(resolved)

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

        model_key = self._get_model_key_from_context(context)
        resolver = self._assignment_resolvers.get(model_key) if model_key else None

        if resolver is None:
            for attr in ("is_assigned", "is_assigned_to"):
                candidate = getattr(obj, attr, None)
                if callable(candidate):
                    resolver = candidate
                    break

        if resolver is not None:
            resolved = self._apply_context_resolver(resolver, context, obj)
            if resolved is not None:
                return bool(resolved)

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
        self.invalidate_user_cache(user)

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
            self.invalidate_user_cache(user)

            logger.info(f"Rôle '{role_name}' retiré de l'utilisateur {user.username}")
        except group_model.DoesNotExist:
            logger.warning(f"Groupe '{role_name}' non trouvé")


def require_role(required_roles: Union[str, list[str]]):
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
        while hasattr(graphql_type, "of_type"):
            graphql_type = graphql_type.of_type
        graphene_type = getattr(graphql_type, "graphene_type", None)
        meta = getattr(graphene_type, "_meta", None)
        model = getattr(meta, "model", None)
        if model is not None:
            return model
        return getattr(graphene_type, "model_class", None)

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
                "operation",
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
                operation=context.get("operation"),
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
        if context.additional_context is None:
            context.additional_context = {}
        if info is not None and isinstance(context.additional_context, dict):
            context.additional_context.setdefault("request", getattr(info, "context", None))
        if context.operation is None and info is not None:
            try:
                op_value = info.operation.operation.value if info.operation else None
            except Exception:
                op_value = None
            if op_value:
                if op_value == "query":
                    context.operation = "read"
                elif op_value == "mutation":
                    context.operation = "write"
                else:
                    context.operation = op_value

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
