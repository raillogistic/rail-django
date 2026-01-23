"""
GraphQL security middleware.
"""

import logging
from graphql import DocumentNode, GraphQLError, GraphQLResolveInfo

from ...core.services import get_rate_limiter
from ..api import security, EventType, Outcome
from .analyzer import GraphQLSecurityAnalyzer
from .config import SecurityConfig

logger = logging.getLogger(__name__)


def create_security_middleware(config: SecurityConfig = None):
    """
    Crée un middleware de sécurité GraphQL.

    Args:
        config: Configuration de sécurité

    Returns:
        Fonction middleware
    """
    analyzer = GraphQLSecurityAnalyzer(config)
    def security_middleware(next_middleware, root, info: GraphQLResolveInfo, **args):
        """
        Middleware de sécurité pour GraphQL.

        Args:
            next_middleware: Middleware suivant
            root: Objet racine
            info: Informations de résolution GraphQL
            **args: Arguments supplémentaires

        Returns:
            Résultat du middleware suivant
        """
        path = getattr(info, "path", None)
        is_root_field = path is None or getattr(path, "prev", None) is None
        user = getattr(info.context, "user", None)

        if is_root_field:
            schema_name = getattr(info.context, "schema_name", None)
            limiter = get_rate_limiter(schema_name)
            result = limiter.check("graphql", request=info.context)
            if not result.allowed:
                request = getattr(info.context, "request", None) or info.context
                security.rate_limited(request, limit_type="graphql_global")
                raise GraphQLError("Limite de taux depassee")

        # Analyser la requete si c'est le champ racine
        if is_root_field:
            try:
                fragments = list(getattr(info, "fragments", {}).values())
                document = DocumentNode(definitions=[info.operation] + fragments)
                analysis = analyzer.analyze_query(
                    document,
                    info.schema,
                    user,
                    info.variable_values,
                )

                if analysis.blocked_reasons:
                    request = getattr(info.context, "request", None) or info.context
                    security.emit(
                        EventType.QUERY_BLOCKED_COMPLEXITY,
                        request=request,
                        outcome=Outcome.BLOCKED,
                        action=f"Query blocked: {'; '.join(analysis.blocked_reasons)}",
                        context={
                            "complexity": analysis.complexity,
                            "depth": analysis.depth,
                            "reasons": analysis.blocked_reasons
                        }
                    )
                    raise GraphQLError(f"Requête bloquée: {'; '.join(analysis.blocked_reasons)}")

                # Ajouter les métriques au contexte
                info.context.security_analysis = analysis

            except GraphQLError:
                raise
            except Exception as e:
                logger.error(f"Erreur d'analyse de sécurité: {e}")

        return next_middleware(root, info, **args)

    return security_middleware
