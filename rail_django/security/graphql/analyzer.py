"""
GraphQL query security analyzer.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from graphql import (
    DocumentNode,
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    GraphQLSchema,
    InlineFragmentNode,
    OperationDefinitionNode,
)

from .config import SecurityConfig, SecurityThreatLevel

logger = logging.getLogger(__name__)


@dataclass
class QueryAnalysisResult:
    """Résultat de l'analyse d'une requête."""
    complexity: int
    depth: int
    field_count: int
    operation_count: int
    has_introspection: bool
    introspection_only: bool
    has_mutations: bool
    execution_time_estimate: float
    threat_level: SecurityThreatLevel
    warnings: list[str]
    blocked_reasons: list[str]


class GraphQLSecurityAnalyzer:
    """
    Analyseur de sécurité pour les requêtes GraphQL.
    """

    def __init__(self, config: SecurityConfig = None):
        """
        Initialise l'analyseur de sécurité.

        Args:
            config: Configuration de sécurité
        """
        self.config = config or SecurityConfig()
        self._field_costs = {}
        self._type_costs = {}

        # Coûts par défaut pour certains types de champs
        self._default_field_costs = {
            'id': 1,
            'createdAt': 1,
            'updatedAt': 1,
            'name': 1,
            'title': 1,
            'description': 2,
            'content': 3,
            'email': 2,
            'phone': 2,
        }

    def analyze_query(self, document: DocumentNode, schema: GraphQLSchema,
                      user=None, variables: dict = None) -> QueryAnalysisResult:
        """
        Analyse une requête GraphQL pour détecter les problèmes de sécurité.

        Args:
            document: Document GraphQL à analyser
            schema: Schéma GraphQL
            user: Utilisateur effectuant la requête
            variables: Variables de la requête

        Returns:
            Résultat de l'analyse de sécurité
        """
        start_time = time.time()

        # Initialiser le résultat
        result = QueryAnalysisResult(
            complexity=0,
            depth=0,
            field_count=0,
            operation_count=0,
            has_introspection=False,
            introspection_only=True,
            has_mutations=False,
            execution_time_estimate=0.0,
            threat_level=SecurityThreatLevel.LOW,
            warnings=[],
            blocked_reasons=[]
        )

        # Analyser chaque opération
        fragments = {
            definition.name.value: definition
            for definition in document.definitions
            if isinstance(definition, FragmentDefinitionNode)
        }

        for definition in document.definitions:
            if isinstance(definition, OperationDefinitionNode):
                result.operation_count += 1

                # Analyser le type d'opération
                if definition.operation.value == 'mutation':
                    result.has_mutations = True

                # Analyser la sélection
                self._analyze_selection_set(
                    definition.selection_set,
                    schema,
                    result,
                    depth=1,
                    parent_type=schema.query_type if definition.operation.value == 'query' else schema.mutation_type,
                    fragments=fragments,
                )

        if not result.has_introspection:
            result.introspection_only = False

        # Calculer le temps d'exécution estimé
        result.execution_time_estimate = time.time() - start_time

        # Déterminer le niveau de menace
        result.threat_level = self._calculate_threat_level(result)

        # Vérifier les limites de sécurité
        self._check_security_limits(result, user)

        return result

    def _analyze_selection_set(self, selection_set, schema: GraphQLSchema,
                               result: QueryAnalysisResult, depth: int,
                               parent_type=None, fragments: Optional[dict[str, Any]] = None):
        """
        Analyse un ensemble de sélections GraphQL.

        Args:
            selection_set: Ensemble de sélections à analyser
            schema: Schéma GraphQL
            result: Résultat de l'analyse à mettre à jour
            depth: Profondeur actuelle
            parent_type: Type parent
        """
        if not selection_set or not selection_set.selections:
            return

        # Mettre à jour la profondeur maximale
        result.depth = max(result.depth, depth)

        for selection in selection_set.selections:
            if isinstance(selection, FieldNode):
                result.field_count += 1

                # Vérifier l'introspection
                if selection.name.value in ['__schema', '__type', '__typename']:
                    result.has_introspection = True
                elif depth == 1:
                    result.introspection_only = False

                # Calculer la complexité du champ
                field_complexity = self._calculate_field_complexity(
                    selection, parent_type, depth
                )
                result.complexity += field_complexity

                # Analyser les sous-sélections
                if selection.selection_set:
                    field_type = self._get_field_type(selection, parent_type, schema)
                    self._analyze_selection_set(
                        selection.selection_set,
                        schema,
                        result,
                        depth + 1,
                        field_type,
                        fragments,
                    )

            elif isinstance(selection, InlineFragmentNode):
                self._analyze_selection_set(
                    selection.selection_set,
                    schema,
                    result,
                    depth,
                    parent_type,
                    fragments,
                )

            elif isinstance(selection, FragmentSpreadNode):
                if fragments:
                    fragment = fragments.get(selection.name.value)
                    if fragment:
                        self._analyze_selection_set(
                            fragment.selection_set,
                            schema,
                            result,
                            depth,
                            parent_type,
                            fragments,
                        )

    def _calculate_field_complexity(self, field: FieldNode, parent_type, depth: int) -> int:
        """
        Calcule la complexité d'un champ.

        Args:
            field: Nœud de champ GraphQL
            parent_type: Type parent
            depth: Profondeur du champ

        Returns:
            Complexité calculée du champ
        """
        base_complexity = 1
        field_name = field.name.value

        # Coût de base du champ
        if field_name in self._default_field_costs:
            base_complexity = self._default_field_costs[field_name]

        # Multiplicateurs basés sur le type de champ
        multiplier = 1.0

        # Champs de connexion (pagination)
        if 'connection' in field_name.lower() or 'edges' in field_name.lower():
            multiplier *= self.config.complexity_multipliers.get('connection', 2.0)

        # Champs de liste
        if field.arguments:
            for arg in field.arguments:
                if arg.name.value in ['first', 'last', 'limit']:
                    # Augmenter la complexité basée sur la taille de la liste
                    try:
                        limit_value = int(arg.value.value)
                        multiplier *= min(limit_value / 10, 10)  # Cap à 10x
                    except (ValueError, AttributeError):
                        multiplier *= 2.0

        # Pénalité de profondeur
        depth_penalty = 1 + (depth * 0.1)

        # Champs imbriqués
        if field.selection_set:
            multiplier *= self.config.complexity_multipliers.get('nested_object', 1.5)

        return int(base_complexity * multiplier * depth_penalty)

    def _get_field_type(self, field: FieldNode, parent_type, schema: GraphQLSchema):
        """
        Récupère le type d'un champ.

        Args:
            field: Nœud de champ
            parent_type: Type parent
            schema: Schéma GraphQL

        Returns:
            Type du champ
        """
        if not parent_type or not hasattr(parent_type, 'fields'):
            return None

        field_name = field.name.value
        if field_name in parent_type.fields:
            field_def = parent_type.fields[field_name]
            return field_def.type

        return None

    def _calculate_threat_level(self, result: QueryAnalysisResult) -> SecurityThreatLevel:
        """
        Calcule le niveau de menace d'une requête.

        Args:
            result: Résultat de l'analyse

        Returns:
            Niveau de menace calculé
        """
        score = 0

        # Complexité
        if result.complexity > self.config.max_query_complexity * 0.8:
            score += 3
        elif result.complexity > self.config.max_query_complexity * 0.5:
            score += 2
        elif result.complexity > self.config.max_query_complexity * 0.3:
            score += 1

        # Profondeur
        if result.depth > self.config.max_query_depth * 0.8:
            score += 3
        elif result.depth > self.config.max_query_depth * 0.5:
            score += 2

        # Nombre de champs
        if result.field_count > self.config.max_field_count * 0.8:
            score += 2
        elif result.field_count > self.config.max_field_count * 0.5:
            score += 1

        # Introspection
        if result.has_introspection:
            score += 2

        # Mutations
        if result.has_mutations:
            score += 1

        # Déterminer le niveau
        if score >= 8:
            return SecurityThreatLevel.CRITICAL
        elif score >= 5:
            return SecurityThreatLevel.HIGH
        elif score >= 3:
            return SecurityThreatLevel.MEDIUM
        else:
            return SecurityThreatLevel.LOW

    def _check_security_limits(self, result: QueryAnalysisResult, user=None):
        """
        Vérifie les limites de sécurité et ajoute des avertissements/blocages.

        Args:
            result: Résultat de l'analyse à mettre à jour
            user: Utilisateur effectuant la requête
        """
        # Vérifier la complexité
        if self.config.enable_query_cost_analysis:
            if result.complexity > self.config.max_query_complexity:
                result.blocked_reasons.append(
                    f"Complexité de requête trop élevée: {result.complexity} > {self.config.max_query_complexity}"
                )
            elif result.complexity > self.config.max_query_complexity * 0.8:
                result.warnings.append(
                    f"Complexité de requête élevée: {result.complexity}"
                )
    
        # Vérifier la profondeur
        if self.config.enable_depth_limiting and not (
            result.introspection_only and self.config.enable_introspection
        ):
            if result.depth > self.config.max_query_depth:
                result.blocked_reasons.append(
                    f"Profondeur de requête trop élevée: {result.depth} > {self.config.max_query_depth}"
                )
            elif result.depth > self.config.max_query_depth * 0.8:
                result.warnings.append(
                    f"Profondeur de requête élevée: {result.depth}"
                )
    
        # Vérifier le nombre de champs
        if result.field_count > self.config.max_field_count:
            result.blocked_reasons.append(
                f"Trop de champs demandés: {result.field_count} > {self.config.max_field_count}"
            )

        # Vérifier l'introspection
        if result.has_introspection and not self.config.enable_introspection:
            if user:
                from ..rbac import role_manager
                user_roles = role_manager.get_user_roles(user)
                if not any(role in self.config.introspection_roles for role in user_roles):
                    result.blocked_reasons.append(
                        "Introspection non autorisée pour cet utilisateur"
                    )
            else:
                result.blocked_reasons.append(
                    "Introspection non autorisée"
                )

        # Vérifier le nombre d'opérations
        if result.operation_count > self.config.max_operation_count:
            result.blocked_reasons.append(
                f"Trop d'opérations: {result.operation_count} > {self.config.max_operation_count}"
            )
