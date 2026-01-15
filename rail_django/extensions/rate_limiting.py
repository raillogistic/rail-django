"""
Purpose: Provide a lightweight GraphQL rate limiting middleware for the project
Args: N/A (module defines middleware callable used by Graphene)
Returns: N/A (exports `rate_limit_middleware` for Graphene middleware chain)
Raises: GraphQLError when rate limit exceeded; otherwise no explicit exceptions
Example:
    >>> # In schema setup
    >>> # schema = graphene.Schema(query=Query, mutation=Mutation,
    >>> #                            middleware=[rate_limit_middleware])
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from graphql import GraphQLError
import graphene

from rail_django.config_proxy import get_settings_proxy
from rail_django.core.services import get_rate_limiter

logger = logging.getLogger(__name__)


def _is_root_field(info: Any) -> bool:
    path = getattr(info, "path", None)
    if path is None:
        return True
    return getattr(path, "prev", None) is None


def _get_rate_limit_settings(schema_name: Optional[str] = None) -> dict[str, Any]:
    """
    Purpose: Retrieve rate limiting settings from hierarchical settings proxy
    Args: None
    Returns: Dict[str, Any]: settings dictionary with keys enable, window_seconds, max_requests, scope
    Raises: None
    Example:
        >>> rl = _get_rate_limit_settings()
        >>> rl.get("enable", False)
        False
    """
    if not schema_name:
        proxy = get_settings_proxy()
        schema_name = proxy.get("DEFAULT_SCHEMA") or "default"
    limiter = get_rate_limiter(schema_name)
    if not limiter.is_enabled("graphql"):
        return {
            "enable": False,
            "window_seconds": 60,
            "max_requests": 0,
            "scope": "user_or_ip",
        }

    rules = limiter.get_rules("graphql")
    if not rules:
        return {
            "enable": False,
            "window_seconds": 60,
            "max_requests": 0,
            "scope": "user_or_ip",
        }

    preferred = [rule for rule in rules if rule.scope in {"user_or_ip", "user"}]
    candidate_rules = preferred or rules
    rule = sorted(candidate_rules, key=lambda r: (r.window_seconds, r.limit))[0]
    return {
        "enable": True,
        "window_seconds": int(rule.window_seconds),
        "max_requests": int(rule.limit),
        "scope": rule.scope,
    }


def rate_limit_middleware(next_fn, root, info, **kwargs):
    """
    Purpose: Graphene middleware to enforce per-request rate limits at root fields
    Args:
        next_fn: callable, next resolver in chain
        root: Any, resolver root
        info: GraphQL ResolveInfo, contains context and field_name
        kwargs: Dict, resolver arguments
    Returns:
        Any: resolver result when allowed, otherwise raises GraphQLError
    Raises:
        GraphQLError: when the request exceeds configured rate limits
    Example:
        >>> # Register in schema setup
        >>> # schema = graphene.Schema(query=Query, mutation=Mutation,
        >>> #                            middleware=[rate_limit_middleware])
    """
    try:
        schema_name = getattr(info.context, "schema_name", None)
        limiter = get_rate_limiter(schema_name)
        if not limiter.is_enabled("graphql"):
            return next_fn(root, info, **kwargs)

        if not _is_root_field(info):
            return next_fn(root, info, **kwargs)

        result = limiter.check("graphql", request=info.context)
        if not result.allowed:
            raise GraphQLError("Rate limit exceeded. Please retry later.")

        field_name = getattr(info, "field_name", "") or ""
        if field_name.lower() == "login":
            login_result = limiter.check("graphql_login", request=info.context)
            if not login_result.allowed:
                raise GraphQLError("Rate limit exceeded. Please retry later.")

        return next_fn(root, info, **kwargs)
    except GraphQLError:
        raise
    except Exception as exc:
        # Fail-open to avoid breaking requests due to middleware issues
        logger.warning(f"Rate limit middleware error: {exc}")
        return next_fn(root, info, **kwargs)


class GraphQLSecurityMiddleware:
    """
    Purpose: Graphene-compatible middleware that applies security checks (rate limiting)
    Args: None (reads configuration via settings proxy)
    Returns: Callable that Graphene can use in the middleware chain
    Raises: GraphQLError when rate limit is exceeded
    Example:
        >>> middleware = [GraphQLSecurityMiddleware()]
        >>> # pass middleware to GraphQL execution environment
    """

    def __call__(self, next_fn, root, info, **kwargs):
        """
        Purpose: Invoke rate limiting before resolver execution
        Args:
            next_fn: Callable next resolver
            root: Any root value
            info: GraphQL ResolveInfo
            kwargs: Resolver arguments
        Returns:
            Any: Resolver result
        Raises:
            GraphQLError: If rate limit is exceeded
        Example:
            >>> GraphQLSecurityMiddleware()(next_fn, root, info, **kwargs)
        """
        return rate_limit_middleware(next_fn, root, info, **kwargs)


class RateLimitInfo(graphene.ObjectType):
    """
    Purpose: GraphQL type describing current rate limiting configuration
    Args: N/A
    Returns: N/A (GraphQL type)
    Raises: None
    Example:
        >>> # Used as a field in SecurityQuery
    """

    enable = graphene.Boolean(description="Whether rate limiting is enabled")
    window_seconds = graphene.Int(
        description="Time window in seconds for counting requests"
    )
    max_requests = graphene.Int(
        description="Max requests allowed within the time window"
    )
    scope = graphene.String(description="Rate limit scope (per_user or per_ip)")


class SecurityQuery(graphene.ObjectType):
    """
    Purpose: Expose security-related queries, currently rate limiting configuration
    Args: N/A
    Returns: N/A (GraphQL query type)
    Raises: None
    Example:
        >>> query { rate_limiting { enable window_seconds max_requests scope } }
    """

    rate_limiting = graphene.Field(
        RateLimitInfo,
        description="Rate limiting configuration for the current schema",
    )

    @staticmethod
    def resolve_rate_limiting(info):
        """
        Purpose: Resolver that returns current rate limiting configuration
        Args:
            info (graphene.ResolveInfo): GraphQL resolve info
        Returns:
            RateLimitInfo: Current configuration as GraphQL type
        Raises:
            None
        Example:
            >>> SecurityQuery.resolve_rate_limiting(info)
        """
        schema_name = getattr(info.context, "schema_name", None)
        config = _get_rate_limit_settings(schema_name)
        # Map keys directly to GraphQL fields
        return RateLimitInfo(
            enable=bool(config.get("enable", False)),
            window_seconds=int(config.get("window_seconds", 60)),
            max_requests=int(config.get("max_requests", 100)),
            scope=str(config.get("scope", "per_user")),
        )


__all__ = [
    "GraphQLSecurityMiddleware",
    "SecurityQuery",
    "rate_limit_middleware",
]
