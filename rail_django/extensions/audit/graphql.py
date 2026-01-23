"""
GraphQL mutations and inputs for Audit.
"""

from datetime import datetime, timezone
import graphene
from graphql import GraphQLError

from ...security import security, EventType, Severity, Outcome
from ...security.context import get_client_ip


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
        default_value="info",
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

        severity_raw = str(input.get("severity") or "info").lower()
        severity_map = {
            "low": Severity.INFO,
            "medium": Severity.WARNING,
            "high": Severity.ERROR,
            "critical": Severity.CRITICAL,
            "info": Severity.INFO,
            "warning": Severity.WARNING,
            "error": Severity.ERROR,
            "debug": Severity.DEBUG,
        }
        severity = severity_map.get(severity_raw, Severity.INFO)

        additional_data = {
            "app_name": input.get("app_name"),
            "model_name": input.get("model_name"),
            "operation": input.get("operation"),
            "component": input.get("component"),
            "roles": input.get("roles") or [],
            "metadata": input.get("metadata") or {},
            "description": input.get("description"),
            "source_route": input.get("source_route"),
        }

        try:
            security.emit(
                EventType.UI_ACTION,
                request=request,
                severity=severity,
                outcome=Outcome.SUCCESS if input.get("success", True) else Outcome.FAILURE,
                context=additional_data,
                resource_type="ui_component",
                resource_name=input.get("component"),
                action=input.get("operation"),
            )
            return LogFrontendAuditMutation(ok=True, error=None)
        except Exception as exc:
            return LogFrontendAuditMutation(
                ok=False, error="Impossible d'enregistrer l'audit."
            )
