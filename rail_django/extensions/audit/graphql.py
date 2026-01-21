"""
GraphQL mutations and inputs for Audit.
"""

from datetime import datetime, timezone
import graphene
from graphql import GraphQLError

from .types import AuditEventType, AuditSeverity, AuditEvent
from .logger import audit_logger


class FrontendAuditEventInput(graphene.InputObjectType):
    """Input GraphQL pour tracer les actions de l'interface utilisateur."""

    app_name = graphene.String(required=True, description="Nom de l'application ciblée")
    model_name = graphene.String(required=True, description="Nom du modèle ciblé")
    operation = graphene.String(required=True, description="Action métier déclenchée")
    component = graphene.String(
        required=True, description="Composant UI source de l'action"
    )
    description = graphene.String(description="Description libre de l'action")
    severity = graphene.String(
        description="Niveau de gravité (low, medium, high, critical)",
        default_value=AuditSeverity.LOW.value,
    )
    metadata = graphene.JSONString(
        description="Données additionnelles pour aider à la corrélation"
    )
    success = graphene.Boolean(
        description="Indique si l'action a été réalisée avec succès",
        default_value=True,
    )
    source_route = graphene.String(
        description="Route frontend depuis laquelle l'action a été initiée"
    )
    roles = graphene.List(
        graphene.String,
        description="Liste des rôles/permissions détenus côté UI",
    )


class LogFrontendAuditMutation(graphene.Mutation):
    """Mutation GraphQL permettant de journaliser une action utilisateur côté frontend."""

    class Arguments:
        input = graphene.Argument(FrontendAuditEventInput, required=True)

    ok = graphene.Boolean()
    error = graphene.String()

    @staticmethod
    def mutate(root, info, input: dict):
        request = getattr(info, "context", None)
        if request is None:
            raise GraphQLError("Contexte de requête invalide.")
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise GraphQLError(
                "Authentification requise pour journaliser cette action."
            )
        severity_raw = str(input.get("severity") or AuditSeverity.LOW.value).upper()
        severity = AuditSeverity.__members__.get(severity_raw, AuditSeverity.LOW)

        additional_data = {
            "app_name": input.get("app_name"),
            "model_name": input.get("model_name"),
            "operation": input.get("operation"),
            "component": input.get("component"),
            "roles": input.get("roles") or [],
            "metadata": input.get("metadata") or {},
            "description": input.get("description"),
        }

        event = AuditEvent(
            event_type=AuditEventType.UI_ACTION,
            severity=severity,
            user_id=getattr(user, "id", None),
            username=getattr(user, "get_username", lambda: None)(),
            client_ip=audit_logger._get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "Unknown"),
            timestamp=datetime.now(timezone.utc),
            request_path=input.get("source_route") or getattr(request, "path", "/"),
            request_method=getattr(request, "method", "UI"),
            additional_data=additional_data,
            success=bool(input.get("success", True)),
        )
        try:
            audit_logger.log_event(event)
            return LogFrontendAuditMutation(ok=True, error=None)
        except Exception as exc:
            return LogFrontendAuditMutation(
                ok=False, error="Impossible d'enregistrer l'audit."
            )
