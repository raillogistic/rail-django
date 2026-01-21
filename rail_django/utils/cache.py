"""
Cache utilities for Rail Django.

This module provides consistent caching utilities used throughout
the framework including key generation, timeouts, and decorators.
"""

import hashlib
import functools
from typing import Any, Callable, Optional, TypeVar, List

from django.core.cache import cache

T = TypeVar("T")


def make_cache_key(prefix: str, *components: str) -> str:
    """
    Generate a cache key from prefix and components.

    Args:
        prefix: Cache key prefix.
        *components: Additional components to include in the key.

    Returns:
        A properly formatted cache key.

    Examples:
        >>> make_cache_key("metadata", "app", "Model")
        "rail_django:metadata:app:Model"
    """
    parts = [p for p in components if p]
    if parts:
        return f"rail_django:{prefix}:{':'.join(parts)}"
    return f"rail_django:{prefix}"


def make_hashed_cache_key(prefix: str, *components: str, max_length: int = 200) -> str:
    """
    Generate a cache key with hashing for long components.

    Args:
        prefix: Cache key prefix.
        *components: Additional components to include in the key.
        max_length: Maximum key length before hashing.

    Returns:
        A properly formatted cache key.

    Examples:
        >>> key = make_hashed_cache_key("query", "very_long_query_string...")
    """
    key = make_cache_key(prefix, *components)
    if len(key) <= max_length:
        return key

    # Hash the components
    hash_input = ":".join(components).encode("utf-8")
    hash_value = hashlib.sha256(hash_input).hexdigest()[:32]
    return f"rail_django:{prefix}:{hash_value}"


def get_cache_timeout(settings_key: str, default: Optional[int] = None) -> Optional[int]:
    """
    Get cache timeout from settings.

    Args:
        settings_key: The settings key to look up.
        default: Default timeout if not configured.

    Returns:
        Cache timeout in seconds or None for no expiry.
    """
    try:
        from django.conf import settings
        rail_settings = getattr(settings, "RAIL_DJANGO", {})
        cache_settings = rail_settings.get("CACHE", {})
        return cache_settings.get(settings_key, default)
    except Exception:
        return default


def get_user_cache_key(user: Any) -> Optional[str]:
    """
    Generate a cache key component for a user.

    Args:
        user: User object or None.

    Returns:
        User-specific cache key component or None.
    """
    if user is None:
        return None
    if hasattr(user, "is_authenticated") and not user.is_authenticated:
        return "anonymous"
    if hasattr(user, "pk"):
        return f"user:{user.pk}"
    if hasattr(user, "id"):
        return f"user:{user.id}"
    return None


def cache_result(
    timeout: Optional[int] = 300,
    key_prefix: str = "cache",
    key_func: Optional[Callable[..., str]] = None,
    cache_none: bool = False,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to cache function results.

    Args:
        timeout: Cache timeout in seconds.
        key_prefix: Prefix for cache keys.
        key_func: Custom function to generate cache key from arguments.
        cache_none: Whether to cache None results.

    Returns:
        Decorated function with caching.

    Examples:
        >>> @cache_result(timeout=60, key_prefix="my_func")
        ... def expensive_function(arg1, arg2):
        ...     return compute_expensive_result(arg1, arg2)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                key_parts = [str(a) for a in args]
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = make_hashed_cache_key(key_prefix, func.__name__, *key_parts)

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Check for cached None
            if cache_none:
                none_marker = cache.get(f"{cache_key}:none")
                if none_marker:
                    return None

            # Compute result
            result = func(*args, **kwargs)

            # Cache result
            if result is not None:
                cache.set(cache_key, result, timeout)
            elif cache_none:
                cache.set(f"{cache_key}:none", True, timeout)

            return result

        wrapper.cache_clear = lambda: None  # Placeholder for compatibility
        return wrapper

    return decorator


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalidate all cache keys matching a pattern.

    Note: This is a best-effort operation. Not all cache backends support
    pattern-based deletion.

    Args:
        pattern: Pattern to match (e.g., "rail_django:metadata:*").

    Returns:
        Number of keys deleted (if supported) or 0.
    """
    try:
        # Try to get the cache backend
        cache_backend = cache

        # Check for Redis-like backends with pattern support
        if hasattr(cache_backend, "delete_pattern"):
            return cache_backend.delete_pattern(pattern)

        # Check for keys method (some backends)
        if hasattr(cache_backend, "keys"):
            keys = cache_backend.keys(pattern)
            if keys:
                cache.delete_many(keys)
                return len(keys)

        return 0
    except Exception:
        return 0


def invalidate_cache_keys(keys: List[str]) -> None:
    """
    Invalidate specific cache keys.

    Args:
        keys: List of cache keys to invalidate.
    """
    if keys:
        cache.delete_many(keys)


def get_or_set(
    key: str,
    default_func: Callable[[], T],
    timeout: Optional[int] = 300,
) -> T:
    """
    Get a value from cache or compute and set it.

    Args:
        key: Cache key.
        default_func: Function to compute default value.
        timeout: Cache timeout in seconds.

    Returns:
        Cached or computed value.
    """
    result = cache.get(key)
    if result is None:
        result = default_func()
        if result is not None:
            cache.set(key, result, timeout)
    return result
