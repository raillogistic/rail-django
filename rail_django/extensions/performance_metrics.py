"""
Advanced Performance Metrics System for Django GraphQL Auto

This module provides comprehensive performance monitoring including:
- Query execution time distributions (p95, p99)
- Most frequently used queries tracking
- Slow query detection and logging
- Query depth and complexity analysis
- Real-time performance analytics
"""

import hashlib
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from graphene import Boolean, Field, Float, Int
from graphene import List as GrapheneList
from graphene import ObjectType, String
from graphql import Visitor, parse, validate, visit
from graphql.language.ast import FieldNode, FragmentDefinitionNode, OperationDefinitionNode

logger = logging.getLogger(__name__)


@dataclass
class QueryExecutionMetrics:
    """Métriques d'exécution d'une requête individuelle."""
    query_hash: str
    query_name: str
    query_text: str
    execution_time: float
    timestamp: datetime
    user_id: Optional[str] = None
    query_depth: int = 0
    query_complexity: int = 0
    database_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    memory_usage_mb: float = 0.0
    error_message: Optional[str] = None
    is_slow_query: bool = False
    is_complex_query: bool = False


@dataclass
class QueryFrequencyStats:
    """Statistiques de fréquence d'une requête."""
    query_hash: str
    query_name: str
    query_text: str
    call_count: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    min_execution_time: float = float('inf')
    max_execution_time: float = 0.0
    last_executed: Optional[datetime] = None
    error_count: int = 0
    success_rate: float = 100.0


@dataclass
class PerformanceDistribution:
    """Distribution des temps d'exécution."""
    p50: float = 0.0  # Médiane
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    min_time: float = 0.0
    max_time: float = 0.0
    avg_time: float = 0.0
    total_requests: int = 0


@dataclass
class SlowQueryAlert:
    """Alerte pour requête lente."""
    query_hash: str
    query_name: str
    execution_time: float
    threshold: float
    timestamp: datetime
    user_id: Optional[str] = None
    query_complexity: int = 0
    database_queries: int = 0


class QueryComplexityAnalyzer:
    """Analyseur de complexité des requêtes GraphQL."""

    def __init__(self, max_depth: int = 10, complexity_weights: Dict[str, int] = None):
        self.max_depth = max_depth
        self.complexity_weights = complexity_weights or {
            'field': 1,
            'list_field': 2,
            'connection': 3,
            'nested_object': 2,
            'fragment': 1
        }

    def analyze_query(self, query_text: str) -> Tuple[int, int]:
        """
        Analyse la profondeur et la complexité d'une requête.

        Returns:
            Tuple[int, int]: (depth, complexity)
        """
        try:
            document = parse(query_text)
            analyzer = ComplexityVisitor(self.complexity_weights)
            visit(document, analyzer)

            return analyzer.max_depth, analyzer.total_complexity

        except Exception as e:
            logger.warning(f"Failed to analyze query complexity: {e}")
            return 0, 0


class ComplexityVisitor(Visitor):
    """Visiteur pour calculer la complexité des requêtes GraphQL."""

    def __init__(self, complexity_weights: Dict[str, int]):
        # Initialize parent Visitor class to set up enter_leave_map
        super().__init__()

        self.complexity_weights = complexity_weights
        self.current_depth = 0
        self.max_depth = 0
        self.total_complexity = 0
        self.field_stack = []

    def enter_field(self, node: FieldNode, *_):
        """Entrée dans un champ."""
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.field_stack.append(node.name.value)

        # Calculer la complexité du champ
        field_complexity = self.complexity_weights.get('field', 1)

        # Augmenter la complexité pour les listes et connexions
        if self._is_list_field(node):
            field_complexity = self.complexity_weights.get('list_field', 2)
        elif self._is_connection_field(node):
            field_complexity = self.complexity_weights.get('connection', 3)

        # Multiplier par la profondeur pour pénaliser les requêtes profondes
        self.total_complexity += field_complexity * self.current_depth

    def leave_field(self, node: FieldNode, *_):
        """Sortie d'un champ."""
        self.current_depth -= 1
        if self.field_stack:
            self.field_stack.pop()

    def _is_list_field(self, node: FieldNode) -> bool:
        """Vérifie si le champ est une liste."""
        field_name = node.name.value
        return field_name.startswith('all') or field_name.endswith('s')

    def _is_connection_field(self, node: FieldNode) -> bool:
        """Vérifie si le champ est une connexion Relay."""
        return any(arg.name.value in ['first', 'last', 'after', 'before']
                   for arg in (node.arguments or []))


class PerformanceMetricsCollector:
    """Collecteur de métriques de performance avancées."""

    def __init__(self,
                 max_history_size: int = 10000,
                 slow_query_threshold: float = 1.0,
                 complex_query_threshold: int = 100):
        self.max_history_size = max_history_size
        self.slow_query_threshold = slow_query_threshold
        self.complex_query_threshold = complex_query_threshold

        # Stockage des métriques
        self.execution_history: deque = deque(maxlen=max_history_size)
        self.query_frequency: Dict[str, QueryFrequencyStats] = {}
        self.slow_query_alerts: deque = deque(maxlen=1000)

        # Analyseur de complexité
        self.complexity_analyzer = QueryComplexityAnalyzer()

        # Thread safety
        self._lock = Lock()

        # Cache pour les distributions
        self._distribution_cache = {}
        self._cache_expiry = {}

    def record_query_execution(self,
                               query_text: str,
                               execution_time: float,
                               user_id: Optional[str] = None,
                               database_queries: int = 0,
                               cache_hits: int = 0,
                               cache_misses: int = 0,
                               memory_usage_mb: float = 0.0,
                               error_message: Optional[str] = None) -> None:
        """Enregistre l'exécution d'une requête."""

        with self._lock:
            # Générer un hash pour identifier la requête
            query_hash = self._generate_query_hash(query_text)
            query_name = self._extract_query_name(query_text)

            # Analyser la complexité
            depth, complexity = self.complexity_analyzer.analyze_query(query_text)

            # Déterminer si c'est une requête lente ou complexe
            is_slow = execution_time > self.slow_query_threshold
            is_complex = complexity > self.complex_query_threshold

            # Créer les métriques d'exécution
            metrics = QueryExecutionMetrics(
                query_hash=query_hash,
                query_name=query_name,
                query_text=query_text,
                execution_time=execution_time,
                timestamp=datetime.now(timezone.utc),
                user_id=user_id,
                query_depth=depth,
                query_complexity=complexity,
                database_queries=database_queries,
                cache_hits=cache_hits,
                cache_misses=cache_misses,
                memory_usage_mb=memory_usage_mb,
                error_message=error_message,
                is_slow_query=is_slow,
                is_complex_query=is_complex
            )

            # Ajouter à l'historique
            self.execution_history.append(metrics)

            # Mettre à jour les statistiques de fréquence
            self._update_frequency_stats(metrics)

            # Générer une alerte si nécessaire
            if is_slow:
                self._generate_slow_query_alert(metrics)

            # Invalider le cache des distributions
            self._invalidate_distribution_cache()

    def get_execution_time_distribution(self,
                                        time_window_minutes: int = 60) -> PerformanceDistribution:
        """Obtient la distribution des temps d'exécution."""

        cache_key = f"distribution_{time_window_minutes}"

        # Vérifier le cache
        if (cache_key in self._distribution_cache and
            cache_key in self._cache_expiry and
                datetime.now() < self._cache_expiry[cache_key]):
            return self._distribution_cache[cache_key]

        with self._lock:
            # Filtrer les métriques dans la fenêtre de temps
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
            recent_metrics = [
                m for m in self.execution_history
                if m.timestamp >= cutoff_time and not m.error_message
            ]

            if not recent_metrics:
                return PerformanceDistribution()

            # Extraire les temps d'exécution
            execution_times = [m.execution_time for m in recent_metrics]
            execution_times.sort()

            # Calculer les percentiles
            distribution = PerformanceDistribution(
                p50=statistics.median(execution_times),
                p75=self._percentile(execution_times, 75),
                p90=self._percentile(execution_times, 90),
                p95=self._percentile(execution_times, 95),
                p99=self._percentile(execution_times, 99),
                min_time=min(execution_times),
                max_time=max(execution_times),
                avg_time=statistics.mean(execution_times),
                total_requests=len(execution_times)
            )

            # Mettre en cache
            self._distribution_cache[cache_key] = distribution
            self._cache_expiry[cache_key] = datetime.now() + timedelta(minutes=5)

            return distribution

    def get_most_frequent_queries(self, limit: int = 10) -> List[QueryFrequencyStats]:
        """Obtient les requêtes les plus fréquentes."""
        with self._lock:
            sorted_queries = sorted(
                self.query_frequency.values(),
                key=lambda q: q.call_count,
                reverse=True
            )
            return sorted_queries[:limit]

    def get_slowest_queries(self, limit: int = 10) -> List[QueryFrequencyStats]:
        """Obtient les requêtes les plus lentes."""
        with self._lock:
            sorted_queries = sorted(
                self.query_frequency.values(),
                key=lambda q: q.avg_execution_time,
                reverse=True
            )
            return sorted_queries[:limit]

    def get_recent_slow_queries(self, limit: int = 20) -> List[SlowQueryAlert]:
        """Obtient les alertes de requêtes lentes récentes."""
        with self._lock:
            return list(self.slow_query_alerts)[-limit:]

    def get_complexity_stats(self) -> Dict[str, Any]:
        """Obtient les statistiques de complexité."""
        with self._lock:
            if not self.execution_history:
                return {}

            complexities = [
                m.query_complexity for m in self.execution_history if m.query_complexity > 0]
            depths = [m.query_depth for m in self.execution_history if m.query_depth > 0]

            if not complexities or not depths:
                return {}

            return {
                'avg_complexity': statistics.mean(complexities),
                'max_complexity': max(complexities),
                'avg_depth': statistics.mean(depths),
                'max_depth': max(depths),
                'complex_queries_count': len([c for c in complexities if c > self.complex_query_threshold]),
                'deep_queries_count': len([d for d in depths if d > 7])
            }

    def _generate_query_hash(self, query_text: str) -> str:
        """Génère un hash pour identifier une requête."""
        # Normaliser la requête (supprimer les espaces, etc.)
        normalized = ' '.join(query_text.split())
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def _extract_query_name(self, query_text: str) -> str:
        """Extrait le nom de la requête."""
        try:
            document = parse(query_text)
            for definition in document.definitions:
                if isinstance(definition, OperationDefinitionNode):
                    if definition.name:
                        return definition.name.value
                    # Si pas de nom, utiliser le premier champ
                    if definition.selection_set and definition.selection_set.selections:
                        first_field = definition.selection_set.selections[0]
                        if isinstance(first_field, FieldNode):
                            return first_field.name.value
            return "anonymous_query"
        except Exception:
            return "invalid_query"

    def _update_frequency_stats(self, metrics: QueryExecutionMetrics) -> None:
        """Met à jour les statistiques de fréquence."""
        query_hash = metrics.query_hash

        if query_hash not in self.query_frequency:
            self.query_frequency[query_hash] = QueryFrequencyStats(
                query_hash=query_hash,
                query_name=metrics.query_name,
                query_text=metrics.query_text
            )

        stats = self.query_frequency[query_hash]
        stats.call_count += 1
        stats.total_execution_time += metrics.execution_time
        stats.avg_execution_time = stats.total_execution_time / stats.call_count
        stats.min_execution_time = min(stats.min_execution_time, metrics.execution_time)
        stats.max_execution_time = max(stats.max_execution_time, metrics.execution_time)
        stats.last_executed = metrics.timestamp

        if metrics.error_message:
            stats.error_count += 1

        stats.success_rate = ((stats.call_count - stats.error_count) / stats.call_count) * 100

    def _generate_slow_query_alert(self, metrics: QueryExecutionMetrics) -> None:
        """Génère une alerte pour requête lente."""
        alert = SlowQueryAlert(
            query_hash=metrics.query_hash,
            query_name=metrics.query_name,
            execution_time=metrics.execution_time,
            threshold=self.slow_query_threshold,
            timestamp=metrics.timestamp,
            user_id=metrics.user_id,
            query_complexity=metrics.query_complexity,
            database_queries=metrics.database_queries
        )

        self.slow_query_alerts.append(alert)

        # Logger l'alerte
        logger.warning(
            f"Slow query detected: {metrics.query_name} "
            f"took {metrics.execution_time:.2f}s "
            f"(threshold: {self.slow_query_threshold}s)"
        )

    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calcule un percentile."""
        if not data:
            return 0.0

        k = (len(data) - 1) * (percentile / 100)
        f = int(k)
        c = k - f

        if f == len(data) - 1:
            return data[f]

        return data[f] * (1 - c) + data[f + 1] * c

    def _invalidate_distribution_cache(self) -> None:
        """Invalide le cache des distributions."""
        self._distribution_cache.clear()
        self._cache_expiry.clear()


# Instance globale du collecteur de métriques
performance_collector = PerformanceMetricsCollector()


# Types GraphQL pour les métriques de performance
class PerformanceDistributionType(ObjectType):
    """Type GraphQL pour la distribution des performances."""
    p50 = Float(description="50e percentile (médiane)")
    p75 = Float(description="75e percentile")
    p90 = Float(description="90e percentile")
    p95 = Float(description="95e percentile")
    p99 = Float(description="99e percentile")
    min_time = Float(description="Temps minimum")
    max_time = Float(description="Temps maximum")
    avg_time = Float(description="Temps moyen")
    total_requests = Int(description="Nombre total de requêtes")


class QueryFrequencyStatsType(ObjectType):
    """Type GraphQL pour les statistiques de fréquence des requêtes."""
    query_hash = String(description="Hash de la requête")
    query_name = String(description="Nom de la requête")
    query_text = String(description="Texte de la requête")
    call_count = Int(description="Nombre d'appels")
    avg_execution_time = Float(description="Temps d'exécution moyen")
    min_execution_time = Float(description="Temps d'exécution minimum")
    max_execution_time = Float(description="Temps d'exécution maximum")
    last_executed = String(description="Dernière exécution")
    error_count = Int(description="Nombre d'erreurs")
    success_rate = Float(description="Taux de succès")


class SlowQueryAlertType(ObjectType):
    """Type GraphQL pour les alertes de requêtes lentes."""
    query_hash = String(description="Hash de la requête")
    query_name = String(description="Nom de la requête")
    execution_time = Float(description="Temps d'exécution")
    threshold = Float(description="Seuil de lenteur")
    timestamp = String(description="Horodatage")
    user_id = String(description="ID utilisateur")
    query_complexity = Int(description="Complexité de la requête")
    database_queries = Int(description="Nombre de requêtes DB")


class ComplexityStatsType(ObjectType):
    """Type GraphQL pour les statistiques de complexité."""
    avg_complexity = Float(description="Complexité moyenne")
    max_complexity = Int(description="Complexité maximale")
    avg_depth = Float(description="Profondeur moyenne")
    max_depth = Int(description="Profondeur maximale")
    complex_queries_count = Int(description="Nombre de requêtes complexes")
    deep_queries_count = Int(description="Nombre de requêtes profondes")
