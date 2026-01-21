"""
Decorators for query optimization.
"""

import time
from functools import wraps
from typing import Callable, Optional

from django.db.models import QuerySet
from graphql import DocumentNode, GraphQLResolveInfo

from .optimizer import get_optimizer
from .monitor import get_performance_monitor
from .cache import _resolve_cache_scopes, _build_query_cache_key


def optimize_query(
    enable_caching: bool = False,
    cache_timeout: Optional[int] = None,
    user_specific_cache: bool = False,
    complexity_limit: Optional[int] = None,
    cache_scopes: Optional[list[str]] = None,
):
    """
    Decorator for optimizing GraphQL queries.
    """

    def decorator(resolver_func: Callable) -> Callable:
        @wraps(resolver_func)
        def wrapper(root, info: GraphQLResolveInfo, **kwargs):
            schema_name = getattr(info.context, "schema_name", None)
            optimizer = get_optimizer(schema_name)
            performance_monitor = get_performance_monitor(schema_name)
            cache_backend = None
            cache_config = getattr(optimizer, "config", None)
            cache_enabled = bool(
                enable_caching or getattr(cache_config, "enable_query_caching", False)
            )
            if cache_enabled:
                from ...core.services import get_query_cache_backend
                cache_backend = get_query_cache_backend(schema_name)

            # DÇ¸marrer le monitoring
            start_time = time.time()

            try:
                # Analyser la complexitÇ¸ si une limite est dÇ¸finie
                if complexity_limit is not None:
                    from ...security.graphql_security import (
                        GraphQLSecurityAnalyzer,
                        SecurityConfig,
                    )

                    fragments = list(getattr(info, "fragments", {}).values())
                    from graphql import DocumentNode
                    document = DocumentNode(definitions=[info.operation] + fragments)
                    analyzer = GraphQLSecurityAnalyzer(
                        SecurityConfig(
                            max_query_complexity=int(complexity_limit),
                            enable_query_cost_analysis=True,
                        )
                    )
                    analysis = analyzer.analyze_query(
                        document,
                        info.schema,
                        getattr(info.context, "user", None),
                        info.variable_values,
                    )
                    if analysis.complexity > complexity_limit:
                        raise Exception(
                            f"Query complexity {analysis.complexity} exceeds limit {complexity_limit}"
                        )

                # ExÇ¸cuter la requÇºte
                if (
                    cache_enabled
                    and cache_backend is not None
                    and info.operation
                    and info.operation.operation.value == "query"
                ):
                    cache_timeout_value = cache_timeout
                    if cache_timeout_value is None and cache_config is not None:
                        cache_timeout_value = getattr(cache_config, "cache_timeout", None)

                    cache_user_specific = bool(
                        user_specific_cache
                        or getattr(cache_config, "query_cache_user_specific", False)
                    )
                    user = getattr(info.context, "user", None)
                    user_id = None
                    if cache_user_specific and user and getattr(user, "is_authenticated", False):
                        user_id = str(getattr(user, "id", None) or getattr(user, "pk", None))

                    scope_setting = getattr(cache_config, "query_cache_scope", "schema")
                    scopes = _resolve_cache_scopes(scope_setting, schema_name, cache_scopes)
                    versions = [cache_backend.get_version(scope) for scope in scopes]
                    cache_buster = getattr(info.context, "cache_buster", None) or getattr(
                        info.context, "cache_version", None
                    )

                    cache_key = _build_query_cache_key(
                        info,
                        schema_name=schema_name,
                        versions=versions,
                        user_id=user_id,
                        cache_buster=cache_buster,
                    )
                    cached = cache_backend.get(cache_key)
                    if cached is not None:
                        return cached

                result = resolver_func(root, info, **kwargs)

                # Optimize queryset if it's a QuerySet
                if isinstance(result, QuerySet) and hasattr(result, "model"):
                    result = optimizer.optimize_queryset(result, info, result.model)
                if (
                    cache_enabled
                    and cache_backend is not None
                    and info.operation
                    and info.operation.operation.value == "query"
                    and result is not None
                    and not isinstance(result, QuerySet)
                ):
                    cache_timeout_value = cache_timeout
                    if cache_timeout_value is None and cache_config is not None:
                        cache_timeout_value = getattr(cache_config, "cache_timeout", None)
                    cache_user_specific = bool(
                        user_specific_cache
                        or getattr(cache_config, "query_cache_user_specific", False)
                    )
                    user = getattr(info.context, "user", None)
                    user_id = None
                    if cache_user_specific and user and getattr(user, "is_authenticated", False):
                        user_id = str(getattr(user, "id", None) or getattr(user, "pk", None))
                    scope_setting = getattr(cache_config, "query_cache_scope", "schema")
                    scopes = _resolve_cache_scopes(scope_setting, schema_name, cache_scopes)
                    versions = [cache_backend.get_version(scope) for scope in scopes]
                    cache_buster = getattr(info.context, "cache_buster", None) or getattr(
                        info.context, "cache_version", None
                    )
                    cache_key = _build_query_cache_key(
                        info,
                        schema_name=schema_name,
                        versions=versions,
                        user_id=user_id,
                        cache_buster=cache_buster,
                    )
                    cache_backend.set(cache_key, result, timeout=cache_timeout_value)

                # Enregistrer les mÇ¸triques de performance
                execution_time = time.time() - start_time
                performance_monitor.record_query_performance(
                    query_name=info.field_name,
                    execution_time=execution_time,
                    cache_hit=False,
                )

                return result

            except Exception as e:
                # Enregistrer l'erreur
                execution_time = time.time() - start_time
                performance_monitor.record_query_performance(
                    query_name=info.field_name,
                    execution_time=execution_time,
                    cache_hit=False,
                    error=str(e),
                )
                raise

        return wrapper

    return decorator
