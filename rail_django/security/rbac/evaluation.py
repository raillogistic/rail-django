"""
Permission evaluation mixin for the RoleManager.

This module provides the core permission evaluation logic including
policy integration, contextual permission checks, ownership/assignment
resolution, and audit logging.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, Union

from django.db import models

from .types import PermissionContext, PermissionExplanation, PolicyDecisionDetail

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class PermissionEvaluationMixin:
    """
    Mixin providing permission evaluation capabilities for RoleManager.

    Handles policy engine integration, contextual permission evaluation,
    object ownership/assignment checks, and permission auditing.
    """

    _policy_engine_enabled: bool
    _permission_audit_enabled: bool
    _permission_audit_log_all: bool
    _permission_audit_log_denies: bool
    _owner_resolvers: dict[str, Callable[[PermissionContext], bool]]
    _assignment_resolvers: dict[str, Callable[[PermissionContext], bool]]
    _context_resolver_version: int

    # --- Context Resolution Methods ---

    def register_owner_resolver(
        self,
        model_class: Union[type[models.Model], str],
        resolver: Callable[[PermissionContext], bool],
    ) -> None:
        """Register a custom ownership resolver for a model."""
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
        """Register a custom assignment resolver for a model."""
        key = self._normalize_model_key(model_class)
        if not key:
            return
        self._assignment_resolvers[key] = resolver
        self._context_resolver_version += 1

    def _normalize_model_key(
        self, model_class: Union[type[models.Model], str, None]
    ) -> str:
        """Normalize a model class or string to a consistent lowercase key."""
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
        """Extract and normalize the model key from a permission context."""
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
        """Apply a context resolver with flexible signature support."""
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

    def _get_context_instance(
        self, context: PermissionContext
    ) -> Optional[models.Model]:
        """Get the object instance from a permission context."""
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
        """Check if the user in the context owns the object."""
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
        """Check if the object is assigned to the user in the context."""
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
        if hasattr(obj, "assigned_to"):
            assigned_to = obj.assigned_to
            if assigned_to == user:
                return True
            return getattr(assigned_to, "pk", assigned_to) == getattr(user, "pk", user)

        if hasattr(obj, "assignees"):
            try:
                assignees = obj.assignees.all()
            except Exception:
                return False
            return user in assignees
        return False

    # --- Policy Context Building ---

    def _build_policy_context(
        self,
        user: "AbstractUser",
        permission: str,
        context: Optional[PermissionContext],
    ):
        """Build a PolicyContext for the policy engine evaluation."""
        from ..policies import PolicyContext as AccessPolicyContext

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
        """Convert a policy object to a PolicyDecisionDetail."""
        return PolicyDecisionDetail(
            name=str(getattr(policy, "name", "")),
            effect=str(
                getattr(getattr(policy, "effect", None), "value", None)
                or getattr(policy, "effect", "")
            ),
            priority=int(getattr(policy, "priority", 0) or 0),
            reason=getattr(policy, "reason", None),
        )

    # --- Permission Evaluation ---

    def _check_contextual_permission_with_reason(
        self, permission: str, context: PermissionContext
    ) -> tuple[bool, Optional[str]]:
        """Check contextual permissions and return the reason for the decision."""
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
        """Core permission evaluation logic."""
        from ..policies import PolicyEffect, policy_manager

        explanation = None
        if include_explanation:
            explanation = PermissionExplanation(permission=permission, allowed=False)

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
                        explanation.reason = decision.reason or (
                            "policy_allow"
                            if decision.effect == PolicyEffect.ALLOW
                            else "policy_deny"
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

        if self._permission_in_effective_permissions(permission, effective_permissions):
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
        """Log a permission decision to the audit system."""
        if explanation is None:
            return
        try:
            from ..api import security, EventType, Outcome
        except Exception:
            return

        request = None
        if context and isinstance(context.additional_context, dict):
            request = context.additional_context.get(
                "request"
            ) or context.additional_context.get("context")

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
                context.object_id or getattr(context.object_instance, "pk", "") or ""
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

        event_type = (
            EventType.AUTHZ_PERMISSION_GRANTED
            if explanation.allowed
            else EventType.AUTHZ_PERMISSION_DENIED
        )
        outcome = Outcome.SUCCESS if explanation.allowed else Outcome.DENIED

        security.emit(
            event_type,
            request=request,
            outcome=outcome,
            context=additional_data,
            resource_type="model" if model_label else "permission",
            resource_name=model_label or permission,
            resource_id=object_id,
            action=f"Permission {'granted' if explanation.allowed else 'denied'}: {permission}",
        )

    # --- Public API ---

    def has_permission(
        self,
        user: "AbstractUser",
        permission: str,
        context: PermissionContext = None,
    ) -> bool:
        """Check if a user has a specific permission."""
        audit_enabled = self._permission_audit_enabled and (
            self._permission_audit_log_all or self._permission_audit_log_denies
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
            self._audit_permission_decision(user, permission, context, explanation)

        return allowed

    def explain_permission(
        self, user: "AbstractUser", permission: str, context: PermissionContext = None
    ) -> PermissionExplanation:
        """Get a detailed explanation of a permission decision."""
        allowed, explanation = self._evaluate_permission(
            user, permission, context, include_explanation=True
        )
        if explanation is None:
            explanation = PermissionExplanation(permission=permission, allowed=allowed)
        return explanation

    def _check_contextual_permission(
        self, user: "AbstractUser", permission: str, context: PermissionContext
    ) -> bool:
        """Check contextual permissions without returning reason."""
        allowed, _ = self._check_contextual_permission_with_reason(permission, context)
        return allowed


__all__ = ["PermissionEvaluationMixin"]
