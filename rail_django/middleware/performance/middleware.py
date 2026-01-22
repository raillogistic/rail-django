"""
Middleware for GraphQL performance monitoring.
"""

import json
import logging
import time
from typing import Optional

from django.conf import settings
from django.db import connection
from django.utils.deprecation import MiddlewareMixin

from .aggregator import get_performance_aggregator
from .collectors import QueryMetricsCollector
from .metrics import RequestMetrics
from ...extensions.optimization import get_performance_monitor

logger = logging.getLogger(__name__)


class GraphQLPerformanceMiddleware(MiddlewareMixin):
    """
    Middleware for monitoring GraphQL request performance.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self.enabled = getattr(settings, "GRAPHQL_PERFORMANCE_ENABLED", settings.DEBUG)
        self.aggregator = get_performance_aggregator() if self.enabled else None
        self.performance_monitor = get_performance_monitor() if self.enabled else None
        perf_settings = getattr(settings, "RAIL_DJANGO_GRAPHQL", {}).get(
            "performance_settings", {}
        )
        self.enable_query_metrics = bool(perf_settings.get("enable_query_metrics", False))
        self.enable_n_plus_one_detection = bool(
            perf_settings.get("enable_n_plus_one_detection", True)
        )
        self.n_plus_one_threshold = int(perf_settings.get("n_plus_one_threshold", 5))

    def process_request(self, request):
        """Handle the start of a request."""
        if not self.enabled or not self._is_graphql_request(request):
            return None

        request._graphql_request_id = f"req_{int(time.time() * 1000)}_{id(request)}"
        request._graphql_start_time = time.time()
        query_name = self._resolve_query_name(request)
        request._graphql_query_text = self._extract_query_text(request)

        request._graphql_metrics = RequestMetrics(
            request_id=request._graphql_request_id,
            query_name=query_name,
            start_time=request._graphql_start_time,
            user_id=getattr(request.user, "id", None) if hasattr(request, "user") else None,
        )
        if self.enable_query_metrics and hasattr(connection, "execute_wrapper"):
            collector = QueryMetricsCollector(
                n_plus_one_threshold=self.n_plus_one_threshold
            )
            wrapper = connection.execute_wrapper(collector.execute_wrapper)
            wrapper.__enter__()
            request._graphql_query_metrics = collector
            request._graphql_query_wrapper = wrapper

        return None

    def process_response(self, request, response):
        """Handle the end of a request."""
        if not self.enabled or not hasattr(request, "_graphql_metrics"):
            return response

        end_time = time.time()
        metrics = request._graphql_metrics
        metrics.end_time = end_time
        metrics.execution_time = end_time - metrics.start_time
        self._finalize_query_metrics(request, metrics)

        metrics.cache_hits = 0
        metrics.cache_misses = 0

        if self.aggregator:
            self.aggregator.add_metrics(metrics)

        if getattr(settings, "GRAPHQL_PERFORMANCE_HEADERS", False):
            response["X-GraphQL-Execution-Time"] = f"{metrics.execution_time:.3f}"
            if metrics.query_complexity:
                response["X-GraphQL-Query-Complexity"] = str(metrics.query_complexity)
            if metrics.database_queries:
                response["X-GraphQL-DB-Queries"] = str(metrics.database_queries)
            if metrics.database_time:
                response["X-GraphQL-DB-Time"] = f"{metrics.database_time:.3f}"
            if metrics.n_plus_one_count:
                response["X-GraphQL-N-Plus-One"] = str(metrics.n_plus_one_count)

        return response

    def process_exception(self, request, exception):
        """Handle exceptions."""
        if not self.enabled or not hasattr(request, "_graphql_metrics"):
            return None

        metrics = request._graphql_metrics
        metrics.errors.append(str(exception))

        end_time = time.time()
        metrics.end_time = end_time
        metrics.execution_time = end_time - metrics.start_time
        self._finalize_query_metrics(request, metrics)

        if self.aggregator:
            self.aggregator.add_metrics(metrics)

        return None

    def _finalize_query_metrics(self, request, metrics: RequestMetrics) -> None:
        wrapper = getattr(request, "_graphql_query_wrapper", None)
        if wrapper is not None:
            try:
                wrapper.__exit__(None, None, None)
            except Exception:
                logger.debug("Failed to close query metrics wrapper", exc_info=True)
            request._graphql_query_wrapper = None
        collector = getattr(request, "_graphql_query_metrics", None)
        if collector is None:
            return

        metrics.database_queries = collector.query_count
        metrics.database_time = collector.total_time
        if self.enable_n_plus_one_detection:
            candidates = collector.get_n_plus_one_candidates()
            metrics.n_plus_one_queries = candidates
            metrics.n_plus_one_count = len(candidates)
            if candidates:
                metrics.warnings.append("Potential N+1 query pattern detected")

    def _resolve_query_name(self, request) -> str:
        query_text = self._extract_query_text(request)
        if not query_text:
            return "unknown"
        if request.method == "POST" and request.body:
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                op_name = payload.get("operationName") or payload.get("operation_name")
                if op_name:
                    return str(op_name)
        first_field = self._extract_first_field_name(query_text)
        return first_field or "anonymous"

    def _extract_first_field_name(self, query_text: str) -> Optional[str]:
        tokens = query_text.replace("{", " ").replace("}", " ").split()
        for token in tokens:
            lowered = token.lower()
            if lowered in {"query", "mutation", "subscription"}:
                continue
            if lowered.startswith("fragment"):
                continue
            if token.startswith("$") or token.startswith("..."):
                continue
            return token
        return None

    def _extract_query_text(self, request) -> str:
        if request.method == "GET":
            query = request.GET.get("query", "")
            return str(query) if query is not None else ""
        if not request.body:
            return ""
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            return ""
        if isinstance(payload, dict):
            query = payload.get("query", "")
            return str(query) if query is not None else ""
        return ""

    def _is_graphql_request(self, request) -> bool:
        """Return True when the request targets GraphQL."""
        if request.path.endswith("/graphql/") or request.path.endswith("/graphql"):
            return True
        content_type = getattr(request, "content_type", "")
        return bool(content_type and "graphql" in content_type.lower())
