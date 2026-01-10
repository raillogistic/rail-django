"""
Centralized rate limiting utilities for Rail Django.

This module provides a single rate-limiting engine that can be reused across
HTTP middleware, GraphQL middleware, and API views with consistent policies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_SUPPORTED_SCOPES = {"user", "ip", "user_or_ip", "user_ip", "global"}


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int
    scope: str = "user_or_ip"
    enabled: bool = True


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: Optional[int] = None
    rule: Optional[RateLimitRule] = None
    context: Optional[str] = None


def _normalize_scope(scope: str) -> str:
    if scope in _SUPPORTED_SCOPES:
        return scope
    return "user_or_ip"


def _normalize_rules(context_name: str, raw_rules: Iterable[Dict[str, Any]]) -> List[RateLimitRule]:
    normalized: List[RateLimitRule] = []
    for idx, rule in enumerate(raw_rules or []):
        if not isinstance(rule, dict):
            continue
        name = str(rule.get("name") or f"{context_name}_{idx}")
        limit = int(rule.get("limit", 0) or 0)
        window_seconds = int(rule.get("window_seconds", 0) or 0)
        scope = _normalize_scope(str(rule.get("scope", "user_or_ip")))
        enabled = bool(rule.get("enabled", True))
        normalized.append(
            RateLimitRule(
                name=name,
                limit=limit,
                window_seconds=window_seconds,
                scope=scope,
                enabled=enabled,
            )
        )
    return normalized


def _normalize_config(raw_config: Dict[str, Any]) -> Dict[str, Any]:
    enabled = bool(raw_config.get("enabled", True))
    contexts_raw = raw_config.get("contexts")
    contexts: Dict[str, Dict[str, Any]] = {}
    if isinstance(contexts_raw, dict):
        for context_name, context_cfg in contexts_raw.items():
            if not isinstance(context_cfg, dict):
                continue
            context_enabled = bool(context_cfg.get("enabled", True))
            raw_rules = context_cfg.get("rules") or context_cfg.get("limits") or []
            rules = _normalize_rules(context_name, raw_rules)
            contexts[context_name] = {"enabled": context_enabled, "rules": rules}
    return {"enabled": enabled, "contexts": contexts}


def _merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = {"enabled": base.get("enabled", True), "contexts": dict(base.get("contexts", {}))}
    if "enabled" in override:
        merged["enabled"] = bool(override.get("enabled"))
    override_contexts = override.get("contexts", {})
    if isinstance(override_contexts, dict):
        for context_name, context_cfg in override_contexts.items():
            merged["contexts"][context_name] = context_cfg
    return merged


def _legacy_security_settings() -> Dict[str, Any]:
    config = getattr(settings, "RAIL_DJANGO_GRAPHQL", {}) or {}
    return config.get("security_settings", {}) or {}


def _legacy_schema_security_rate_limit(schema_name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not schema_name:
        return None
    schema_settings = getattr(settings, "RAIL_DJANGO_GRAPHQL_SCHEMAS", {}) or {}
    schema_config = schema_settings.get(schema_name, {}) if isinstance(schema_settings, dict) else {}
    security_settings = schema_config.get("security_settings", {}) if isinstance(schema_config, dict) else {}
    rl = security_settings.get("rate_limiting")
    if isinstance(rl, dict):
        return rl
    return None


def _build_legacy_config(schema_name: Optional[str]) -> Dict[str, Any]:
    contexts: Dict[str, Dict[str, Any]] = {}
    enabled = False

    security_settings = _legacy_security_settings()
    security_rl_enabled = bool(security_settings.get("enable_rate_limiting", False))

    graphql_rules: List[RateLimitRule] = []
    if security_rl_enabled:
        graphql_rules.extend(
            [
                RateLimitRule(
                    name="user_minute",
                    scope="user_or_ip",
                    limit=int(security_settings.get("rate_limit_requests_per_minute", 60)),
                    window_seconds=60,
                ),
                RateLimitRule(
                    name="user_hour",
                    scope="user_or_ip",
                    limit=int(security_settings.get("rate_limit_requests_per_hour", 1000)),
                    window_seconds=3600,
                ),
            ]
        )

    graphql_auth_setting = getattr(settings, "GRAPHQL_ENABLE_AUTH_RATE_LIMITING", None)
    graphql_auth_enabled = graphql_auth_setting is True

    if graphql_auth_enabled:
        graphql_rules.append(
            RateLimitRule(
                name="ip_hour",
                scope="ip",
                limit=int(getattr(settings, "GRAPHQL_REQUESTS_LIMIT", 100)),
                window_seconds=int(getattr(settings, "GRAPHQL_REQUESTS_WINDOW", 3600)),
            )
        )

    schema_rl = _legacy_schema_security_rate_limit(schema_name)
    if schema_rl and bool(schema_rl.get("enable", False)):
        graphql_rules.append(
            RateLimitRule(
                name="schema_rule",
                scope=_normalize_scope(str(schema_rl.get("scope", "user_or_ip"))),
                limit=int(schema_rl.get("max_requests", 100)),
                window_seconds=int(schema_rl.get("window_seconds", 60)),
            )
        )

    if graphql_rules:
        contexts["graphql"] = {"enabled": True, "rules": graphql_rules}
        enabled = True

    if graphql_auth_enabled:
        login_rules = [
            RateLimitRule(
                name="login_ip",
                scope="ip",
                limit=int(getattr(settings, "AUTH_LOGIN_ATTEMPTS_LIMIT", 5)),
                window_seconds=int(getattr(settings, "AUTH_LOGIN_ATTEMPTS_WINDOW", 900)),
            )
        ]
        contexts["graphql_login"] = {"enabled": True, "rules": login_rules}
        enabled = True

    schema_api_cfg = getattr(settings, "GRAPHQL_SCHEMA_API_RATE_LIMIT", {}) or {}
    if isinstance(schema_api_cfg, dict) and bool(schema_api_cfg.get("enable", True)):
        contexts["schema_api"] = {
            "enabled": True,
            "rules": [
                RateLimitRule(
                    name="schema_api",
                    scope=_normalize_scope(str(schema_api_cfg.get("scope", "user_or_ip"))),
                    limit=int(schema_api_cfg.get("max_requests", 60)),
                    window_seconds=int(schema_api_cfg.get("window_seconds", 60)),
                )
            ],
        }
        enabled = True

    return {"enabled": enabled, "contexts": contexts}


def _load_rate_limit_config(schema_name: Optional[str]) -> Dict[str, Any]:
    raw_config = getattr(settings, "RAIL_DJANGO_RATE_LIMITING", None)
    if isinstance(raw_config, dict):
        base = _normalize_config(raw_config)
        schema_overrides = None
        overrides_cfg = getattr(settings, "RAIL_DJANGO_RATE_LIMITING_SCHEMAS", None)
        if isinstance(overrides_cfg, dict) and schema_name in overrides_cfg:
            schema_overrides = overrides_cfg.get(schema_name)
        if isinstance(schema_overrides, dict):
            override_normalized = _normalize_config(schema_overrides)
            return _merge_configs(base, override_normalized)
        return base
    return _build_legacy_config(schema_name)


def _resolve_user(user: Any, request: Any) -> Optional[Any]:
    if user is not None:
        return user if getattr(user, "is_authenticated", False) else None
    if request is None:
        return None
    req_user = getattr(request, "user", None)
    if req_user and getattr(req_user, "is_authenticated", False):
        return req_user
    return None


def _get_client_ip(request: Any) -> Optional[str]:
    if request is None or not hasattr(request, "META"):
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _build_identifier(scope: str, user: Optional[Any], ip: Optional[str]) -> Optional[str]:
    if scope == "global":
        return "global"
    if scope == "user":
        if user is None:
            return None
        user_id = getattr(user, "id", None)
        if user_id is None:
            return None
        return f"user:{user_id}"
    if scope == "ip":
        if not ip:
            return None
        return f"ip:{ip}"
    if scope == "user_ip":
        if user is None or not ip:
            return None
        user_id = getattr(user, "id", None)
        if user_id is None:
            return None
        return f"user:{user_id}:ip:{ip}"
    # user_or_ip fallback
    if user is not None:
        user_id = getattr(user, "id", None)
        if user_id is not None:
            return f"user:{user_id}"
    if ip:
        return f"ip:{ip}"
    return None


def _consume(cache_key: str, limit: int, window_seconds: int, cost: int) -> bool:
    try:
        count = cache.get(cache_key)
    except Exception as exc:
        logger.warning("Rate limit cache error for %s: %s", cache_key, exc)
        return True

    if count is None:
        cache.add(cache_key, int(cost), timeout=window_seconds)
        return True

    if int(count) + int(cost) > int(limit):
        return False

    try:
        cache.incr(cache_key, int(cost))
    except Exception:
        cache.set(cache_key, int(count) + int(cost), timeout=window_seconds)
    return True


def _mark_checked(request: Any, context: str) -> bool:
    if request is None:
        return False
    try:
        checked = getattr(request, "_rail_rate_limit_checked", None)
    except Exception:
        return False
    if checked is None:
        checked = set()
        try:
            setattr(request, "_rail_rate_limit_checked", checked)
        except Exception:
            return False
    if context in checked:
        return True
    checked.add(context)
    return False


class RateLimiter:
    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self._config = _load_rate_limit_config(schema_name)

    def _get_context(self, context: str) -> Optional[Dict[str, Any]]:
        return self._config.get("contexts", {}).get(context)

    def _context_enabled(self, context: str) -> bool:
        if not self._config.get("enabled", True):
            return False
        context_cfg = self._get_context(context)
        if not context_cfg:
            return False
        return bool(context_cfg.get("enabled", True))

    def get_rules(self, context: str) -> List[RateLimitRule]:
        context_cfg = self._get_context(context)
        if not context_cfg:
            return []
        rules = context_cfg.get("rules", [])
        return [rule for rule in rules if isinstance(rule, RateLimitRule)]

    def is_enabled(self, context: str) -> bool:
        return self._context_enabled(context)

    def check(
        self,
        context: str,
        request: Any = None,
        *,
        user: Any = None,
        ip: Optional[str] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        if not context or not self._context_enabled(context):
            return RateLimitResult(allowed=True, context=context)

        if _mark_checked(request, context):
            return RateLimitResult(allowed=True, context=context)

        rules = self.get_rules(context)
        if not rules:
            return RateLimitResult(allowed=True, context=context)

        resolved_user = _resolve_user(user, request)
        resolved_ip = ip or _get_client_ip(request)

        for rule in rules:
            if not rule.enabled or rule.limit <= 0 or rule.window_seconds <= 0:
                continue
            identifier = _build_identifier(rule.scope, resolved_user, resolved_ip)
            if not identifier:
                continue
            cache_key = f"rail:rl:{context}:{rule.name}:{identifier}"
            if not _consume(cache_key, rule.limit, rule.window_seconds, cost):
                return RateLimitResult(
                    allowed=False,
                    retry_after=rule.window_seconds,
                    rule=rule,
                    context=context,
                )

        return RateLimitResult(allowed=True, context=context)


_rate_limiter_cache: Dict[Optional[str], RateLimiter] = {}


def get_rate_limiter(schema_name: Optional[str] = None) -> RateLimiter:
    if schema_name not in _rate_limiter_cache:
        _rate_limiter_cache[schema_name] = RateLimiter(schema_name)
    return _rate_limiter_cache[schema_name]


def clear_rate_limiter_cache() -> None:
    _rate_limiter_cache.clear()
