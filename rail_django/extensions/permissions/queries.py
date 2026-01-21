"""
GraphQL types and queries for permissions.
"""

import graphene
from django.apps import apps
from django.core.exceptions import PermissionDenied
from .base import OperationType
from .manager import permission_manager
from .utils import PermissionContext, role_manager


class PermissionInfo(graphene.ObjectType):
    """Informations sur les permissions d'un utilisateur."""
    model_name = graphene.String(description="Nom du modÇºle")
    verbose_name = graphene.String(description="Nom verbeux du modÇºle")
    can_create = graphene.Boolean(description="Peut crÇ¸er")
    can_read = graphene.Boolean(description="Peut lire")
    can_update = graphene.Boolean(description="Peut modifier")
    can_delete = graphene.Boolean(description="Peut supprimer")
    can_list = graphene.Boolean(description="Peut lister")
    can_history = graphene.Boolean(description="Peut consulter l'historique")


class PolicyDecisionInfo(graphene.ObjectType):
    """DÇ¸tails d'une dÇ¸cision de politique."""
    name = graphene.String()
    effect = graphene.String()
    priority = graphene.Int()
    reason = graphene.String()


class PermissionExplanationInfo(graphene.ObjectType):
    """Explication dÇ¸taillÇ¸e d'une vÇ¸rification de permission."""
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


class PermissionQuery(graphene.ObjectType):
    """Queries pour vÇ¸rifier les permissions."""
    my_permissions = graphene.List(PermissionInfo, model_name=graphene.String(), description="Permissions de l'utilisateur connectÇ¸")
    explain_permission = graphene.Field(PermissionExplanationInfo, permission=graphene.String(required=True), model_name=graphene.String(), object_id=graphene.String(), operation=graphene.String(), description="Explique pourquoi une permission est accordÇ¸e ou refusÇ¸e.")

    def resolve_my_permissions(self, info, model_name: str = None):
        user = getattr(info.context, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            try:
                from ..auth import authenticate_request
                user = authenticate_request(info)
            except Exception: user = None
        if not user or not getattr(user, "is_authenticated", False): return []

        models_to_check = [apps.get_model(model_name)] if model_name else apps.get_models()
        permissions = []
        for model in models_to_check:
            model_label = model._meta.label_lower
            permissions.append(PermissionInfo(
                model_name=model_label, verbose_name=str(model._meta.verbose_name),
                can_create=permission_manager.check_operation_permission(user, model_label, OperationType.CREATE).allowed,
                can_read=permission_manager.check_operation_permission(user, model_label, OperationType.READ).allowed,
                can_update=permission_manager.check_operation_permission(user, model_label, OperationType.UPDATE).allowed,
                can_delete=permission_manager.check_operation_permission(user, model_label, OperationType.DELETE).allowed,
                can_list=permission_manager.check_operation_permission(user, model_label, OperationType.LIST).allowed,
                can_history=permission_manager.check_operation_permission(user, model_label, OperationType.HISTORY).allowed,
            ))
        return permissions

    def resolve_explain_permission(self, info, permission: str, model_name: str = None, object_id: str = None, operation: str = None):
        user = getattr(info.context, "user", None)
        if not user or not getattr(user, "is_authenticated", False): raise PermissionDenied("Authentification requise")
        model_class = apps.get_model(model_name) if model_name else None
        if operation is None and info.operation:
            op_val = getattr(info.operation.operation, "value", None)
            operation = "read" if op_val == "query" else "write" if op_val == "mutation" else op_val
        context = PermissionContext(user=user, model_class=model_class, object_id=object_id, operation=operation, additional_context={"request": getattr(info, "context", None)})
        exp = role_manager.explain_permission(user, permission, context)
        pd = PolicyDecisionInfo(name=exp.policy_decision.name, effect=exp.policy_decision.effect, priority=exp.policy_decision.priority, reason=exp.policy_decision.reason) if exp.policy_decision else None
        pm = [PolicyDecisionInfo(name=m.name, effect=m.effect, priority=m.priority, reason=m.reason) for m in exp.policy_matches]
        return PermissionExplanationInfo(permission=permission, allowed=exp.allowed, reason=exp.reason, policy_decision=pd, policy_matches=pm or None, roles=exp.user_roles or None, effective_permissions=sorted(exp.effective_permissions) if exp.effective_permissions else None, context_required=exp.context_required, context_allowed=exp.context_allowed, context_reason=exp.context_reason, model=model_class._meta.label_lower if model_class else None, object_id=object_id, operation=operation)
