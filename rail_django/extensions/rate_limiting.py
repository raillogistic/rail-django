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

import hashlib
import logging
from typing import Any, Dict, Optional

from django.core.cache import cache
from graphql import GraphQLError
import graphene

from rail_django.conf import get_settings_proxy

logger = logging.getLogger(__name__)


def _build_key(
    scope: str, field_name: str, user_id: Optional[int], ip_addr: Optional[str]
) -> str:
    """
    Purpose: Build a stable cache key for rate limiting
    Args:
        scope (str): either "per_user" or "per_ip"
        field_name (str): GraphQL field being resolved
        user_id (Optional[int]): authenticated user id if available
        ip_addr (Optional[str]): client IP address or None
    Returns:
        str: hashed cache key prefixed with 'gql_rl:'
    Raises:
        None
    Example:
        >>> _build_key("per_user", "createOrder", 42, None)
        'gql_rl:...'
    """
    base = f"{scope}:{field_name}:{user_id or 'anon'}:{ip_addr or 'noip'}"
    return "gql_rl:" + hashlib.sha256(base.encode("utf-8")).hexdigest()


def _get_rate_limit_settings() -> Dict[str, Any]:
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
    proxy = get_settings_proxy()
    schema_name: str = proxy.get("DEFAULT_SCHEMA") or "default"
    rl_settings: Dict[str, Any] = (
        proxy.get(f"schema_settings.{schema_name}.security_settings.rate_limiting")
        or {}
    )
    # Apply sane defaults
    return {
        "enable": bool(rl_settings.get("enable", False)),
        "window_seconds": int(rl_settings.get("window_seconds", 60)),
        "max_requests": int(rl_settings.get("max_requests", 100)),
        "scope": (rl_settings.get("scope") or "per_user"),
    }


def rate_limit_middleware(next_fn, root, info, **kwargs):
    """
    Purpose: Graphene middleware to enforce per-field request rate limits
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
        rl = _get_rate_limit_settings()
        if not rl.get("enable", False):
            return next_fn(root, info, **kwargs)

        user = getattr(info.context, "user", None)
        user_id: Optional[int] = (
            getattr(user, "id", None)
            if (user and getattr(user, "is_authenticated", False))
            else None
        )
        ip_addr: Optional[str] = info.context.META.get(
            "HTTP_X_FORWARDED_FOR", ""
        ).split(",")[0].strip() or info.context.META.get("REMOTE_ADDR")
        scope = rl.get("scope", "per_user")
        key = _build_key(
            scope=scope,
            field_name=getattr(info, "field_name", "unknown"),
            user_id=user_id,
            ip_addr=ip_addr,
        )
        count = cache.get(key, 0)

        if count >= rl.get("max_requests", 100):
            raise GraphQLError("Rate limit exceeded. Please retry later.")

        # Increment with TTL window
        cache.set(key, int(count) + 1, timeout=rl.get("window_seconds", 60))
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
        config = _get_rate_limit_settings()
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
