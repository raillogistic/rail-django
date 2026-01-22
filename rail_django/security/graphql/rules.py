"""
GraphQL security validation rules.
"""

import logging
from graphql import DocumentNode, GraphQLError, ValidationRule
from graphql.validation import ValidationContext

from .analyzer import GraphQLSecurityAnalyzer

logger = logging.getLogger(__name__)


class QueryComplexityValidationRule(ValidationRule):
    """
    Règle de validation pour la complexité des requêtes.
    """

    def __init__(self, analyzer: GraphQLSecurityAnalyzer):
        """
        Initialise la règle de validation.

        Args:
            analyzer: Analyseur de sécurité
        """
        super().__init__()
        self.analyzer = analyzer

    def enter_document(self, node: DocumentNode, *args):
        """
        Valide le document lors de l'entrée.

        Args:
            node: Nœud du document
        """
        context = args[0] if args else None
        if not isinstance(context, ValidationContext):
            return

        schema = context.schema
        user = getattr(context, 'user', None)

        try:
            result = self.analyzer.analyze_query(node, schema, user)

            # Bloquer si nécessaire
            if result.blocked_reasons:
                for reason in result.blocked_reasons:
                    context.report_error(GraphQLError(reason))

            # Logger les avertissements
            for warning in result.warnings:
                logger.warning(f"Avertissement de sécurité GraphQL: {warning}")

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse de sécurité: {e}")
            context.report_error(GraphQLError("Erreur d'analyse de sécurité"))
