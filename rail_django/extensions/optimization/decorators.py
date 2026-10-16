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
            # Result caching is bypassed: arbitrary resolvers contain authorization.
            # DÇ¸marrer le monitoring
            start_time = time.time()

            try:
                # Analyser la complexitÇ¸ si une limite est dÇ¸finie
                if complexity_limit is not None:
                    from ...security.graphql import (
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

                result = resolver_func(root, info, **kwargs)

                # Optimize queryset if it's a QuerySet
                if isinstance(result, QuerySet) and hasattr(result, "model"):
                    result = optimizer.optimize_queryset(result, info, result.model)
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
