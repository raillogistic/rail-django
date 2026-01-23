# Rate Limiting

## Overview

Rail Django integrates a rate limiting system to protect your API against abuse. Rate limiting applies to GraphQL requests, REST endpoints, and can be configured per user, IP, or endpoint.

---

## Table of Contents

1. [Global Configuration](#global-configuration)
2. [Limiting Strategies](#limiting-strategies)
3. [Rate Limiting Contexts](#rate-limiting-contexts)
4. [Response Headers](#response-headers)
5. [Customization](#customization)
6. [Best Practices](#best-practices)

---

## Global Configuration

### Basic Settings

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_rate_limiting": True,
        "rate_limit_requests_per_minute": 60,
        "rate_limit_requests_per_hour": 1000,
    },
    "middleware_settings": {
        "enable_rate_limiting_middleware": True,
    },
}
```

### Advanced Configuration

```python
RAIL_DJANGO_RATE_LIMITING = {
    # ─── Activation ───
    "enabled": True,

    # ─── Storage Backend ───
    "backend": "redis",  # "redis", "memory", or "django_cache"
    "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379/1"),

    # ─── Default Limits ───
    "default_limits": {
        "per_second": None,      # No per-second limit
        "per_minute": 60,
        "per_hour": 1000,
        "per_day": 10000,
    },

    # ─── Identification ───
    "key_function": "rail_django.rate_limiting.get_rate_limit_key",
    "key_prefix": "rl:",

    # ─── Behavior ───
    "include_headers": True,     # Adds X-RateLimit-* headers
    "on_reject": "error",        # "error" or "delay"
    "error_message": "Rate limit exceeded. Please slow down.",

    # ─── Specific Contexts ───
    "contexts": {
        # ... see Contexts section
    },
}
```

---

## Limiting Strategies

### By Authenticated User

```python
RAIL_DJANGO_RATE_LIMITING = {
    "default_limits": {
        "per_minute": 60,
    },
    "key_function": "rail_django.rate_limiting.user_key",
}
```

Rate limit is applied by `user.id` for authenticated users.

### By IP Address

```python
RAIL_DJANGO_RATE_LIMITING = {
    "key_function": "rail_django.rate_limiting.ip_key",
}
```

Uses the client IP (detected via X-Forwarded-For if configured).

### Combined (User or IP)

```python
RAIL_DJANGO_RATE_LIMITING = {
    "key_function": "rail_django.rate_limiting.user_or_ip_key",
}
```

Uses user ID if authenticated, otherwise IP.

### By API Token

```python
def api_token_key(request):
    """
    Rate limit by API token.
    """
    token = request.headers.get("X-API-Token")
    if token:
        return f"token:{token}"
    return f"ip:{get_client_ip(request)}"

RAIL_DJANGO_RATE_LIMITING = {
    "key_function": "myapp.rate_limiting.api_token_key",
}
```

---

## Rate Limiting Contexts

Apply different limits depending on context.

### Context Configuration

```python
RAIL_DJANGO_RATE_LIMITING = {
    "contexts": {
        # Main GraphQL API
        "graphql": {
            "per_minute": 100,
            "per_hour": 2000,
        },

        # Authentication (more restrictive)
        "auth": {
            "per_minute": 10,
            "per_hour": 50,
            "error_message": "Too many login attempts. Please wait.",
        },

        # Schema Management API (admin)
        "schema_api": {
            "per_minute": 30,
            "per_hour": 200,
        },

        # Exports (very limited)
        "export": {
            "per_minute": 5,
            "per_hour": 50,
        },

        # Premium users (more generous)
        "premium": {
            "per_minute": 500,
            "per_hour": 10000,
        },
    },
}
```

### Context Selection

```python
def get_rate_limit_context(request):
    """
    Determines the rate limiting context.
    """
    # Premium users
    if hasattr(request, "user") and request.user.is_premium:
        return "premium"

    # Auth endpoints
    if "/auth/" in request.path:
        return "auth"

    # Export endpoints
    if "/export/" in request.path:
        return "export"

    return "graphql"

RAIL_DJANGO_RATE_LIMITING = {
    "context_function": "myapp.rate_limiting.get_rate_limit_context",
}
```

### Limits by Role

```python
RAIL_DJANGO_RATE_LIMITING = {
    "role_limits": {
        "admin": {
            "per_minute": 500,
            "per_hour": 10000,
        },
        "api_client": {
            "per_minute": 1000,
            "per_hour": 50000,
        },
        "default": {
            "per_minute": 60,
            "per_hour": 1000,
        },
    },
}
```

---

## Response Headers

When `include_headers: True`, responses include:

| Header                  | Description                             |
| ----------------------- | --------------------------------------- |
| `X-RateLimit-Limit`     | Maximum limit for the window            |
| `X-RateLimit-Remaining` | Remaining requests                      |
| `X-RateLimit-Reset`     | Unix timestamp of reset                 |
| `X-RateLimit-Window`    | Window type (minute, hour, day)         |
| `Retry-After`           | Seconds until next attempt (if limited) |

### Response Example

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1705405200
X-RateLimit-Window: minute
```

### Response When Limited

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1705405200
Retry-After: 35
Content-Type: application/json

{
  "errors": [{
    "message": "Rate limit exceeded. Please slow down.",
    "extensions": {
      "code": "RATE_LIMITED",
      "retryAfter": 35
    }
  }]
}
```

---

## Customization

### Custom Key Function

```python
# myapp/rate_limiting.py
def custom_rate_limit_key(request):
    """
    Generates a custom rate limit key.

    The key determines the counting "bucket".
    """
    # By organization
    if hasattr(request, "user") and request.user.organization_id:
        return f"org:{request.user.organization_id}"

    # By IP for anonymous
    return f"ip:{get_client_ip(request)}"
```

### Dynamic Limits

```python
def get_dynamic_limits(request):
    """
    Returns limits based on the user.
    """
    if hasattr(request, "user"):
        tier = getattr(request.user, "subscription_tier", "free")

        if tier == "enterprise":
            return {"per_minute": 1000, "per_hour": 50000}
        elif tier == "pro":
            return {"per_minute": 200, "per_hour": 5000}

    return {"per_minute": 30, "per_hour": 500}

RAIL_DJANGO_RATE_LIMITING = {
    "limits_function": "myapp.rate_limiting.get_dynamic_limits",
}
```

### Exemptions

```python
RAIL_DJANGO_RATE_LIMITING = {
    "exempt_paths": [
        "/health/",
        "/health/ping/",
        "/static/",
    ],
    "exempt_ips": [
        "127.0.0.1",
        "10.0.0.0/8",  # Internal network
    ],
    "exempt_users": [
        "service_account",
    ],
}
```

### Custom Handler

```python
def on_rate_limit_exceeded(request, limit_info):
    """
    Called when limit is exceeded.
    """
    # Log the event
    logger.warning(
        "Rate limit exceeded",
        extra={
            "user_id": getattr(request.user, "id", None),
            "ip": get_client_ip(request),
            "limit": limit_info["limit"],
            "window": limit_info["window"],
        }
    )

    # Optional: alert on severe abuse
    if limit_info["consecutive_hits"] > 10:
        send_abuse_alert(request)

RAIL_DJANGO_RATE_LIMITING = {
    "on_exceed_callback": "myapp.rate_limiting.on_rate_limit_exceeded",
}
```

---

## Best Practices

### 1. Use Redis in Production

```python
# ✅ Redis for distributed rate limiting
RAIL_DJANGO_RATE_LIMITING = {
    "backend": "redis",
    "redis_url": os.environ.get("REDIS_URL"),
}

# ❌ Memory backend doesn't work with multiple workers
# "backend": "memory",  # Only for dev/tests
```

### 2. Differentiate by Context

```python
# ✅ Context-appropriate limits
"contexts": {
    "auth": {"per_minute": 5},      # Very restrictive
    "graphql": {"per_minute": 100}, # Normal
    "export": {"per_minute": 2},    # Very limited
}
```

### 3. Communicate Limits

```python
# ✅ Include headers
"include_headers": True,

# ✅ Clear messages
"error_message": "You have exceeded the request limit. Retry in {retry_after} seconds.",
```

### 4. Exempt Health Checks

```python
"exempt_paths": [
    "/health/",
    "/health/ping/",
    "/health/check/",
],
```

### 5. Monitor Exceeded Limits

```python
# Log rate limits for analysis
"on_exceed_callback": "myapp.monitoring.log_rate_limit",

# Prometheus metrics
"metrics_enabled": True,
```

### 6. Test the Limits

```python
from django.test import TestCase

class RateLimitTests(TestCase):
    def test_rate_limit_exceeded(self):
        for i in range(65):  # Limit = 60/min
            response = self.client.post("/graphql/gql/", ...)

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
```

---

## See Also

- [Optimization](./optimization.md) - Query performance
- [Security](../security/authentication.md) - Authentication
- [Configuration](../graphql/configuration.md) - All settings
