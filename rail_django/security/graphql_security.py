"""
Sécurité spécifique à GraphQL pour Django GraphQL.

Ce module fournit :
- Analyse de complexité des requêtes
- Limitation de profondeur
- Sécurité de l'introspection
- Protection contre les attaques DoS
- Validation des opérations
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, Union

from django.conf import settings
from django.contrib.auth import get_user_model
from graphql import (
    DocumentNode,
    FieldNode,
    FragmentDefinitionNode,
    GraphQLError,
    GraphQLResolveInfo,
    GraphQLSchema,
    InlineFragmentNode,
    OperationDefinitionNode,
    ValidationRule,
    validate,
)
from graphql.language.ast import Node
from graphql.validation import ValidationContext

logger = logging.getLogger(__name__)


class SecurityThreatLevel(Enum):
    """Niveaux de menace de sécurité."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class QueryAnalysisResult:
    """Résultat de l'analyse d'une requête."""
    complexity: int
    depth: int
    field_count: int
    operation_count: int
    has_introspection: bool
    has_mutations: bool
    execution_time_estimate: float
    threat_level: SecurityThreatLevel
    warnings: List[str]
    blocked_reasons: List[str]


@dataclass
class SecurityConfig:
    """Configuration de sécurité GraphQL."""
    max_query_complexity: int = 1000
    max_query_depth: int = 15
    max_field_count: int = 100
    max_operation_count: int = 10
    enable_introspection: bool = False
    introspection_roles: List[str] = None
    query_timeout: int = 30  # secondes
    enable_query_cost_analysis: bool = True
    enable_depth_limiting: bool = True
    enable_field_suggestions: bool = False
    rate_limit_per_minute: int = 60
    complexity_multipliers: Dict[str, float] = None

    def __post_init__(self):
        """Initialise les valeurs par défaut."""
        if self.introspection_roles is None:
            self.introspection_roles = ['admin', 'developer']

        if self.complexity_multipliers is None:
            self.complexity_multipliers = {
                'connection': 2.0,  # Les connexions sont plus coûteuses
                'mutation': 3.0,    # Les mutations sont plus coûteuses
                'nested_object': 1.5,  # Les objets imbriqués
                'list_field': 2.0,  # Les champs de liste
            }


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
                      user=None, variables: Dict = None) -> QueryAnalysisResult:
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
            has_mutations=False,
            execution_time_estimate=0.0,
            threat_level=SecurityThreatLevel.LOW,
            warnings=[],
            blocked_reasons=[]
        )

        # Analyser chaque opération
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
                    parent_type=schema.query_type if definition.operation.value == 'query' else schema.mutation_type
                )

        # Calculer le temps d'exécution estimé
        result.execution_time_estimate = time.time() - start_time

        # Déterminer le niveau de menace
        result.threat_level = self._calculate_threat_level(result)

        # Vérifier les limites de sécurité
        self._check_security_limits(result, user)

        return result

    def _analyze_selection_set(self, selection_set, schema: GraphQLSchema,
                               result: QueryAnalysisResult, depth: int,
                               parent_type=None):
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
                        field_type
                    )

            elif isinstance(selection, InlineFragmentNode):
                self._analyze_selection_set(
                    selection.selection_set,
                    schema,
                    result,
                    depth,
                    parent_type
                )

            elif isinstance(selection, FragmentDefinitionNode):
                self._analyze_selection_set(
                    selection.selection_set,
                    schema,
                    result,
                    depth,
                    parent_type
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
        if result.complexity > self.config.max_query_complexity:
            result.blocked_reasons.append(
                f"Complexité de requête trop élevée: {result.complexity} > {self.config.max_query_complexity}"
            )
        elif result.complexity > self.config.max_query_complexity * 0.8:
            result.warnings.append(
                f"Complexité de requête élevée: {result.complexity}"
            )

        # Vérifier la profondeur
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
                from .rbac import role_manager
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


def create_security_middleware(config: SecurityConfig = None):
    """
    Crée un middleware de sécurité GraphQL.

    Args:
        config: Configuration de sécurité

    Returns:
        Fonction middleware
    """
    analyzer = GraphQLSecurityAnalyzer(config)
    # In-memory rate limit state: {user_id: (count, window_start_ts)}
    rate_limit_state: Dict[int, List[float]] = {}

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
        # Rate limiting without Django cache (in-memory per-process)
        user = getattr(info.context, 'user', None)
        if user and user.is_authenticated:
            now = time.time()
            # state: [count, window_start_ts]
            state = rate_limit_state.get(user.id, [0.0, now])
            count = int(state[0])
            window_start = float(state[1])

            # Reset window if older than 60s
            if now - window_start >= 60.0:
                count = 0
                window_start = now

            if count >= config.rate_limit_per_minute:
                raise GraphQLError("Limite de taux dépassée")

            # Increment and store
            rate_limit_state[user.id] = [float(count + 1), window_start]

        # Analyser la requête si c'est le champ racine
        if info.path.key == info.operation.selection_set.selections[0].name.value:
            try:
                result = analyzer.analyze_query(
                    info.operation,
                    info.schema,
                    user,
                    info.variable_values
                )

                if result.blocked_reasons:
                    raise GraphQLError(f"Requête bloquée: {'; '.join(result.blocked_reasons)}")

                # Ajouter les métriques au contexte
                info.context.security_analysis = result

            except Exception as e:
                logger.error(f"Erreur d'analyse de sécurité: {e}")

        return next_middleware(root, info, **args)

    return security_middleware


def require_introspection_permission(func):
    """
    Décorateur pour protéger les champs d'introspection.

    Args:
        func: Fonction à protéger

    Returns:
        Fonction décorée
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extraire le contexte GraphQL
        info = None
        for arg in args:
            if hasattr(arg, 'context'):
                info = arg
                break

        if not info:
            raise GraphQLError("Contexte GraphQL non disponible")

        user = getattr(info.context, 'user', None)
        if not user or not user.is_authenticated:
            raise GraphQLError("Authentification requise pour l'introspection")

        # Vérifier les permissions d'introspection
        config = getattr(info.context, 'security_config', SecurityConfig())
        if not config.enable_introspection:
            from .rbac import role_manager
            user_roles = role_manager.get_user_roles(user)
            if not any(role in config.introspection_roles for role in user_roles):
                raise GraphQLError("Permission d'introspection requise")

        return func(*args, **kwargs)

    return wrapper


# Configuration par défaut
default_security_config = SecurityConfig(
    max_query_complexity=getattr(settings, 'GRAPHQL_MAX_QUERY_COMPLEXITY', 1000),
    max_query_depth=getattr(settings, 'GRAPHQL_MAX_QUERY_DEPTH', 15),
    max_field_count=getattr(settings, 'GRAPHQL_MAX_FIELD_COUNT', 100),
    enable_introspection=getattr(settings, 'GRAPHQL_ENABLE_INTROSPECTION', False),
    query_timeout=getattr(settings, 'GRAPHQL_QUERY_TIMEOUT', 30),
    rate_limit_per_minute=getattr(settings, 'GRAPHQL_RATE_LIMIT_PER_MINUTE', 60)
)

# Analyseur global
security_analyzer = GraphQLSecurityAnalyzer(default_security_config)
