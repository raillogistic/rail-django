"""
GraphQL types and queries for permission inspection.
"""

from __future__ import annotations

import graphene
from django.apps import apps
from django.core.exceptions import PermissionDenied

from .base import OperationType
from .manager import permission_manager
from .utils import PermissionContext, role_manager


class PermissionInfo(graphene.ObjectType):
    """Permission matrix for one model."""

    model_name = graphene.String(description="Model label")
    verbose_name = graphene.String(description="Human model name")
    can_create = graphene.Boolean(description="Can create records")
    can_read = graphene.Boolean(description="Can read records")
    can_update = graphene.Boolean(description="Can update records")
    can_delete = graphene.Boolean(description="Can delete records")
    can_list = graphene.Boolean(description="Can list records")
    can_history = graphene.Boolean(description="Can view history")


class PolicyDecisionInfo(graphene.ObjectType):
    """Policy decision details."""

    name = graphene.String()
    effect = graphene.String()
    priority = graphene.Int()
    reason = graphene.String()


class PermissionExplanationInfo(graphene.ObjectType):
    """Detailed permission explanation."""

    permission = graphene.String()
    allowed = graphene.Boolean()
    reason = graphene.String()
    policy_decision = graphene.Field(PolicyDecisionInfo)
    policy_matches = graphene.List(PolicyDecisionInfo)
    roles = graphene.List(graphene.String)
    effective_permissions = graphene.List(graphene.String)
    context_required = graphene.Boolean()
    context_allowed = graphene.Boolean()
    context_reason = graphene.String()
    model = graphene.String()
    object_id = graphene.String()
    operation = graphene.String()
    rbac_allowed = graphene.Boolean()
    abac_allowed = graphene.Boolean()
    abac_reason = graphene.String()
    abac_policy = graphene.String()
    hybrid_strategy = graphene.String()


class PermissionQuery(graphene.ObjectType):
    """Permission introspection queries."""

    my_permissions = graphene.List(
        PermissionInfo,
        model_name=graphene.String(),
        description="Permissions for the authenticated user",
    )
    explain_permission = graphene.Field(
        PermissionExplanationInfo,
        permission=graphene.String(required=True),
        model_name=graphene.String(),
        object_id=graphene.String(),
        operation=graphene.String(),
        description="Explain why a permission is granted or denied",
    )

    def resolve_my_permissions(self, info, model_name: str = None):
        user = getattr(info.context, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            try:
                from ..auth import authenticate_request

                user = authenticate_request(info)
            except Exception:
                user = None
        if not user or not getattr(user, "is_authenticated", False):
            return []

        models_to_check = [apps.get_model(model_name)] if model_name else apps.get_models()
        results = []
        for model in models_to_check:
            model_label = model._meta.label_lower
            request = getattr(info, "context", None)
            results.append(
                PermissionInfo(
                    model_name=model_label,
                    verbose_name=str(model._meta.verbose_name),
                    can_create=permission_manager.check_operation_permission(
                        user, model_label, OperationType.CREATE, request=request
                    ).allowed,
                    can_read=permission_manager.check_operation_permission(
                        user, model_label, OperationType.READ, request=request
                    ).allowed,
                    can_update=permission_manager.check_operation_permission(
                        user, model_label, OperationType.UPDATE, request=request
                    ).allowed,
                    can_delete=permission_manager.check_operation_permission(
                        user, model_label, OperationType.DELETE, request=request
                    ).allowed,
                    can_list=permission_manager.check_operation_permission(
                        user, model_label, OperationType.LIST, request=request
                    ).allowed,
                    can_history=permission_manager.check_operation_permission(
                        user, model_label, OperationType.HISTORY, request=request
                    ).allowed,
                )
            )
        return results

    def resolve_explain_permission(
        self,
        info,
        permission: str,
        model_name: str = None,
        object_id: str = None,
        operation: str = None,
    ):
        user = getattr(info.context, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise PermissionDenied("Authentification requise")

        model_class = apps.get_model(model_name) if model_name else None
        if operation is None and info.operation:
            op_val = getattr(info.operation.operation, "value", None)
            operation = (
                "read"
                if op_val == "query"
                else "write"
                if op_val == "mutation"
                else op_val
            )

        context = PermissionContext(
            user=user,
            model_class=model_class,
            object_id=object_id,
            operation=operation,
            additional_context={"request": getattr(info, "context", None)},
        )
        explanation = role_manager.explain_permission(user, permission, context)

        decision = None
        if explanation.policy_decision:
            decision = PolicyDecisionInfo(
                name=explanation.policy_decision.name,
                effect=explanation.policy_decision.effect,
                priority=explanation.policy_decision.priority,
                reason=explanation.policy_decision.reason,
            )

        policy_matches = [
            PolicyDecisionInfo(
                name=match.name,
                effect=match.effect,
                priority=match.priority,
                reason=match.reason,
            )
            for match in explanation.policy_matches
        ]

        return PermissionExplanationInfo(
            permission=permission,
            allowed=explanation.allowed,
            reason=explanation.reason,
            policy_decision=decision,
            policy_matches=policy_matches or None,
            roles=explanation.user_roles or None,
            effective_permissions=sorted(explanation.effective_permissions)
            if explanation.effective_permissions
            else None,
            context_required=explanation.context_required,
            context_allowed=explanation.context_allowed,
            context_reason=explanation.context_reason,
            model=model_class._meta.label_lower if model_class else None,
            object_id=object_id,
            operation=operation,
            rbac_allowed=explanation.rbac_allowed,
            abac_allowed=explanation.abac_allowed,
            abac_reason=explanation.abac_reason,
            abac_policy=explanation.abac_policy,
            hybrid_strategy=explanation.hybrid_strategy,
        )

