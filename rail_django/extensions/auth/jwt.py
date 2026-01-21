"""
JWT token management for authentication.

This module provides classes and functions for generating, verifying,
and refreshing JWT tokens used in authentication flows.
"""

import logging
import threading
import time
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class RefreshTokenStore:
    """
    Cache-backed store for refresh token rotation and reuse detection.

    This class manages refresh token families to support token rotation
    and detect token reuse attacks. It uses Django's cache framework
    with a fallback to in-memory storage.

    Attributes:
        enable_rotation: Whether to rotate refresh tokens on each use.
        enable_reuse_detection: Whether to detect and prevent token reuse.
        cache_alias: The Django cache alias to use.

    Example:
        store = RefreshTokenStore()
        if store.is_family_revoked(family_id):
            raise SecurityError("Token family has been revoked")
    """

    def __init__(self):
        """Initialize the refresh token store with settings from Django config."""
        self.enable_rotation = bool(
            getattr(settings, "JWT_ROTATE_REFRESH_TOKENS", True)
        )
        self.enable_reuse_detection = bool(
            getattr(settings, "JWT_REFRESH_REUSE_DETECTION", True)
        )
        self.cache_alias = getattr(settings, "JWT_REFRESH_TOKEN_CACHE", "default")
        self._cache = self._resolve_cache()
        self._fallback_store: dict[str, dict[str, Any]] = {}
        self._fallback_lock = threading.RLock()

    def _resolve_cache(self):
        """
        Resolve the Django cache backend.

        Returns:
            The cache backend or None if unavailable.
        """
        try:
            from django.core.cache import caches

            return caches[self.cache_alias]
        except Exception:
            return None

    def _cache_get(self, key: str) -> Any:
        """
        Get a value from cache with fallback support.

        Args:
            key: The cache key.

        Returns:
            The cached value or None if not found or expired.
        """
        if self._cache is not None:
            return self._cache.get(key)
        with self._fallback_lock:
            entry = self._fallback_store.get(key)
            if not entry:
                return None
            expires_at = entry.get("expires_at")
            if expires_at is not None and expires_at <= time.time():
                self._fallback_store.pop(key, None)
                return None
            return entry.get("value")

    def _cache_set(self, key: str, value: Any, ttl: Optional[int]) -> None:
        """
        Set a value in cache with fallback support.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Time-to-live in seconds (or None for no expiration).
        """
        if self._cache is not None:
            self._cache.set(key, value, timeout=ttl)
            return
        expires_at = None
        if ttl and ttl > 0:
            expires_at = time.time() + ttl
        with self._fallback_lock:
            self._fallback_store[key] = {"value": value, "expires_at": expires_at}

    def _family_key(self, family_id: str) -> str:
        """Generate the cache key for a token family."""
        return f"jwt:refresh:family:{family_id}"

    def _revoked_key(self, family_id: str) -> str:
        """Generate the cache key for a revoked family."""
        return f"jwt:refresh:revoked:{family_id}"

    def is_family_revoked(self, family_id: str) -> bool:
        """
        Check if a token family has been revoked.

        Args:
            family_id: The unique identifier for the token family.

        Returns:
            True if the family has been revoked, False otherwise.
        """
        return bool(self._cache_get(self._revoked_key(family_id)))

    def revoke_family(self, family_id: str, ttl: Optional[int]) -> None:
        """
        Revoke an entire token family.

        This is typically called when token reuse is detected, to invalidate
        all tokens in the compromised family.

        Args:
            family_id: The unique identifier for the token family.
            ttl: Time-to-live for the revocation marker.
        """
        self._cache_set(self._revoked_key(family_id), True, ttl)

    def ensure_active(
        self, family_id: str, token_id: str, ttl: Optional[int]
    ) -> bool:
        """
        Ensure a token is the currently active one in its family.

        This method checks if the provided token is the most recent one
        in its family. If no token exists for the family, it registers
        this one as active.

        Args:
            family_id: The unique identifier for the token family.
            token_id: The unique identifier for this specific token.
            ttl: Time-to-live for the registration.

        Returns:
            True if this token is active, False if another token is active
            (indicating potential reuse).
        """
        current = self._cache_get(self._family_key(family_id))
        if current is None:
            self._cache_set(self._family_key(family_id), token_id, ttl)
            return True
        return current == token_id

    def rotate(self, family_id: str, token_id: str, ttl: Optional[int]) -> None:
        """
        Rotate to a new token in the family.

        This registers a new token as the active one for the family,
        invalidating any previous tokens.

        Args:
            family_id: The unique identifier for the token family.
            token_id: The unique identifier for the new token.
            ttl: Time-to-live for the registration.
        """
        self._cache_set(self._family_key(family_id), token_id, ttl)


def get_refresh_token_store() -> RefreshTokenStore:
    """
    Get a RefreshTokenStore instance.

    Returns:
        A new RefreshTokenStore instance configured with current settings.
    """
    return RefreshTokenStore()


class JWTManager:
    """
    Manager for JWT token operations.

    This class provides static methods for generating, verifying, and
    refreshing JWT tokens. It handles both access tokens and refresh
    tokens with configurable expiration times.

    Example:
        # Generate tokens for a user
        token_data = JWTManager.generate_token(user)
        access_token = token_data['token']
        refresh_token = token_data['refresh_token']

        # Verify a token
        payload = JWTManager.verify_token(access_token)
        if payload:
            user_id = payload['user_id']

        # Refresh an access token
        new_tokens = JWTManager.refresh_token(refresh_token)
    """

    @staticmethod
    def get_jwt_secret() -> str:
        """
        Retrieve the JWT secret key from Django settings.

        Returns:
            The JWT secret key, falling back to Django's SECRET_KEY.
        """
        return getattr(settings, "JWT_SECRET_KEY", settings.SECRET_KEY)

    @staticmethod
    def get_jwt_expiration() -> int:
        """
        Retrieve the access token expiration duration in seconds.

        Supports non-expiring tokens when configured with 0 or None.
        Accepts either legacy `JWT_EXPIRATION_DELTA` or new
        `JWT_ACCESS_TOKEN_LIFETIME` setting (in seconds).

        Returns:
            The expiration duration in seconds.
        """
        # Prefer explicit access token lifetime if present
        lifetime = getattr(settings, "JWT_ACCESS_TOKEN_LIFETIME", None)
        if lifetime is None:
            lifetime = getattr(settings, "JWT_EXPIRATION_DELTA", 3600 * 72)
        # Normalize types that might be timedelta
        if isinstance(lifetime, timedelta):
            lifetime_seconds = int(lifetime.total_seconds())
        else:
            lifetime_seconds = int(lifetime)
        return lifetime_seconds

    @staticmethod
    def get_refresh_expiration() -> int:
        """
        Retrieve the refresh token expiration duration in seconds.

        Accepts either legacy `JWT_REFRESH_EXPIRATION_DELTA` or new
        `JWT_REFRESH_TOKEN_LIFETIME` setting (in seconds).

        Returns:
            The expiration duration in seconds.
        """
        lifetime = getattr(settings, "JWT_REFRESH_TOKEN_LIFETIME", None)
        if lifetime is None:
            lifetime = getattr(settings, "JWT_REFRESH_EXPIRATION_DELTA", 86400)
        if isinstance(lifetime, timedelta):
            lifetime_seconds = int(lifetime.total_seconds())
        else:
            lifetime_seconds = int(lifetime)
        return lifetime_seconds

    @classmethod
    def generate_token(
        cls,
        user: "AbstractUser",
        *,
        refresh_family: Optional[str] = None,
        include_refresh: bool = True,
    ) -> dict[str, Any]:
        """
        Generate a JWT token for the user.

        Args:
            user: The Django user instance.
            refresh_family: Optional refresh token family identifier for rotation.
            include_refresh: When False, return access token only.

        Returns:
            A dictionary containing:
            - token: The access token string
            - refresh_token: The refresh token string (or None)
            - expires_at: The expiration datetime (or None for non-expiring)
            - permissions: List of user permissions
        """
        # Import here to avoid circular imports
        from .utils import _get_effective_permissions

        now = timezone.now()
        access_lifetime = cls.get_jwt_expiration()
        refresh_lifetime = cls.get_refresh_expiration()

        # If access_lifetime is 0 or negative, treat as non-expiring (no 'exp')
        expiration = (
            None if access_lifetime <= 0 else now + timedelta(seconds=access_lifetime)
        )
        refresh_expiration = (
            now + timedelta(seconds=refresh_lifetime) if include_refresh else None
        )
        permission_snapshot = _get_effective_permissions(user)

        payload = {
            "user_id": user.id,
            "username": user.username,
            "iat": now,
            "type": "access",
            "permissions": permission_snapshot,
        }
        # Only include 'exp' if token should expire
        if expiration is not None:
            payload["exp"] = expiration

        token = jwt.encode(payload, cls.get_jwt_secret(), algorithm="HS256")

        refresh_token = None
        if include_refresh:
            refresh_family_id = refresh_family or uuid.uuid4().hex
            refresh_token_id = uuid.uuid4().hex
            refresh_payload = {
                "user_id": user.id,
                "exp": refresh_expiration,
                "iat": now,
                "type": "refresh",
                "family": refresh_family_id,
                "jti": refresh_token_id,
            }
            refresh_token = jwt.encode(
                refresh_payload, cls.get_jwt_secret(), algorithm="HS256"
            )
            store = get_refresh_token_store()
            if store.enable_rotation or store.enable_reuse_detection:
                store.rotate(refresh_family_id, refresh_token_id, refresh_lifetime)

        return {
            "token": token,
            "refresh_token": refresh_token,
            "expires_at": expiration,
            "permissions": permission_snapshot,
        }

    @classmethod
    def verify_token(
        cls, token: str, expected_type: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """
        Verify and decode a JWT token.

        Args:
            token: The JWT token to verify.
            expected_type: If provided, verify the token type matches.

        Returns:
            The decoded payload dictionary, or None if the token is invalid.
        """
        try:
            payload = jwt.decode(token, cls.get_jwt_secret(), algorithms=["HS256"])
            if expected_type and payload.get("type") != expected_type:
                logger.warning(
                    "Token JWT refused: expected type '%s', got '%s'",
                    expected_type,
                    payload.get("type"),
                )
                return None
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token JWT expire")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token JWT invalide: {e}")
            return None

    @classmethod
    def refresh_token(cls, refresh_token: str) -> Optional[dict[str, Any]]:
        """
        Refresh an access token from a refresh token.

        This method validates the refresh token, checks for reuse attacks,
        and generates a new access token (and optionally a new refresh token
        if rotation is enabled).

        Args:
            refresh_token: The refresh token string.

        Returns:
            A dictionary containing new token data, or None if invalid.
        """
        payload = cls.verify_token(refresh_token, expected_type="refresh")
        if not payload or payload.get("type") != "refresh":
            return None

        store = get_refresh_token_store()
        rotation_enabled = bool(store.enable_rotation)
        reuse_detection = bool(store.enable_reuse_detection and store.enable_rotation)
        family_id = payload.get("family")
        token_id = payload.get("jti")
        refresh_ttl = cls.get_refresh_expiration()

        if reuse_detection:
            if not family_id or not token_id:
                logger.warning("Refresh token missing family/jti")
                return None
            if store.is_family_revoked(family_id):
                logger.warning("Refresh token family revoked")
                return None
            if not store.ensure_active(family_id, token_id, refresh_ttl):
                store.revoke_family(family_id, refresh_ttl)
                logger.warning("Refresh token reuse detected")
                return None

        try:
            User = get_user_model()
            user = User.objects.get(id=payload["user_id"])
            if rotation_enabled:
                token_data = cls.generate_token(user, refresh_family=family_id)
                return token_data

            token_data = cls.generate_token(user, include_refresh=False)
            token_data["refresh_token"] = refresh_token
            return token_data
        except User.DoesNotExist:
            logger.warning(
                f"Utilisateur introuvable pour le refresh token: {payload.get('user_id')}"
            )
            return None
