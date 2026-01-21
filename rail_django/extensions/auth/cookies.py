"""
Cookie handling for JWT authentication.

This module provides functions for managing HTTP-only cookies used
in JWT-based authentication flows.
"""

from typing import Any

from django.conf import settings


def _resolve_cookie_policy(kind: str) -> dict[str, Any]:
    """
    Resolve cookie policy settings for a specific cookie type.

    This function builds a cookie configuration dictionary by checking
    for type-specific settings first, then falling back to general
    JWT cookie settings, and finally to sensible defaults.

    Args:
        kind: The type of cookie ('auth' or 'refresh').

    Returns:
        A dictionary containing cookie policy settings:
        - secure: Whether the cookie should only be sent over HTTPS
        - samesite: The SameSite attribute ('Strict', 'Lax', or 'None')
        - domain: The domain for which the cookie is valid (or None)
        - path: The URL path for which the cookie is valid

    Example:
        policy = _resolve_cookie_policy('auth')
        # Returns: {'secure': True, 'samesite': 'Lax', 'domain': None, 'path': '/'}
    """
    kind_upper = kind.upper()

    # Resolve secure flag with cascading fallbacks
    secure = getattr(settings, f"JWT_{kind_upper}_COOKIE_SECURE", None)
    if secure is None:
        secure = getattr(settings, "JWT_COOKIE_SECURE", None)
    if secure is None:
        secure = not getattr(settings, "DEBUG", False)

    # Force insecure in DEBUG mode for local development
    if getattr(settings, "DEBUG", False):
        secure = False

    # Resolve SameSite attribute
    samesite = getattr(
        settings,
        f"JWT_{kind_upper}_COOKIE_SAMESITE",
        getattr(settings, "JWT_COOKIE_SAMESITE", "Lax"),
    )

    # Resolve domain
    domain = getattr(
        settings,
        f"JWT_{kind_upper}_COOKIE_DOMAIN",
        getattr(settings, "JWT_COOKIE_DOMAIN", None),
    )

    # Resolve path
    path = getattr(
        settings,
        f"JWT_{kind_upper}_COOKIE_PATH",
        "/",
    )

    return {
        "secure": secure,
        "samesite": samesite,
        "domain": domain,
        "path": path,
    }


def set_auth_cookies(request, access_token=None, refresh_token=None):
    """
    Set secure HttpOnly cookies for authentication tokens.

    This function marks cookies to be set on the response. The actual
    cookie setting is handled by middleware that reads the _set_auth_cookies
    attribute from the request object.

    Args:
        request: The Django request object.
        access_token: The JWT access token to set (optional).
        refresh_token: The JWT refresh token to set (optional).

    Note:
        Cookies are set with HttpOnly flag to prevent JavaScript access,
        enhancing security against XSS attacks.

    Example:
        def login_mutation(self, info, username, password):
            user = authenticate(username=username, password=password)
            token_data = JWTManager.generate_token(user)
            set_auth_cookies(
                info.context,
                access_token=token_data['token'],
                refresh_token=token_data['refresh_token'],
            )
            return LoginPayload(ok=True)
    """
    if not hasattr(request, "_set_auth_cookies"):
        request._set_auth_cookies = []

    auth_policy = _resolve_cookie_policy("auth")
    refresh_policy = _resolve_cookie_policy("refresh")

    if access_token:
        request._set_auth_cookies.append(
            {
                "key": getattr(settings, "JWT_AUTH_COOKIE", "jwt"),
                "value": access_token,
                "httponly": True,
                "secure": auth_policy["secure"],
                "samesite": auth_policy["samesite"],
                "domain": auth_policy["domain"],
                "path": auth_policy["path"],
                "max_age": getattr(settings, "JWT_ACCESS_TOKEN_LIFETIME", 3600),
            }
        )

    if refresh_token:
        request._set_auth_cookies.append(
            {
                "key": getattr(settings, "JWT_REFRESH_COOKIE", "refresh_token"),
                "value": refresh_token,
                "httponly": True,
                "secure": refresh_policy["secure"],
                "samesite": refresh_policy["samesite"],
                "domain": refresh_policy["domain"],
                "path": refresh_policy["path"],
                "max_age": getattr(settings, "JWT_REFRESH_TOKEN_LIFETIME", 86400 * 7),
            }
        )


def delete_auth_cookies(request):
    """
    Mark authentication cookies for deletion.

    This function marks cookies to be deleted on the response. The actual
    cookie deletion is handled by middleware that reads the _delete_auth_cookies
    attribute from the request object.

    Args:
        request: The Django request object.

    Note:
        This should be called during logout to ensure tokens are removed
        from the client.

    Example:
        def logout_mutation(self, info):
            delete_auth_cookies(info.context)
            return LogoutPayload(ok=True)
    """
    if not hasattr(request, "_delete_auth_cookies"):
        request._delete_auth_cookies = []

    request._delete_auth_cookies.append(getattr(settings, "JWT_AUTH_COOKIE", "jwt"))
    request._delete_auth_cookies.append(
        getattr(settings, "JWT_REFRESH_COOKIE", "refresh_token")
    )
