import time
import logging
from typing import Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class RedisAnomalyBackend:
    """
    Redis-backed sliding window counter for distributed anomaly detection.

    Uses sorted sets with timestamps as scores for efficient sliding window queries.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client or self._get_default_client()
        self.prefix = getattr(settings, "SECURITY_REDIS_PREFIX", "rail:security:")

    def _get_default_client(self):
        try:
            import redis
            url = getattr(settings, "SECURITY_REDIS_URL", None)
            if url:
                return redis.from_url(url)
            return redis.Redis(
                host=getattr(settings, "SECURITY_REDIS_HOST", "localhost"),
                port=getattr(settings, "SECURITY_REDIS_PORT", 6379),
                db=getattr(settings, "SECURITY_REDIS_DB", 0),
            )
        except ImportError:
            logger.warning("redis package not installed, anomaly detection disabled")
            return None

    def increment_counter(
        self,
        key: str,
        window_seconds: int = 300,
        max_entries: int = 1000
    ) -> Tuple[int, bool]:
        """
        Increment a sliding window counter.

        Returns:
            Tuple of (current_count, is_new_window)
        """
        if not self.redis:
            return 0, False

        full_key = f"{self.prefix}{key}"
        now = time.time()
        window_start = now - window_seconds

        pipe = self.redis.pipeline()
        # Remove old entries outside window
        pipe.zremrangebyscore(full_key, 0, window_start)
        # Add current timestamp
        pipe.zadd(full_key, {str(now): now})
        # Count entries in window
        pipe.zcard(full_key)
        # Set expiry
        pipe.expire(full_key, window_seconds + 60)

        results = pipe.execute()
        count = results[2]

        return count, results[0] > 0  # is_new_window if we removed entries

    def get_counter(self, key: str, window_seconds: int = 300) -> int:
        """Get current count in sliding window."""
        if not self.redis:
            return 0

        full_key = f"{self.prefix}{key}"
        now = time.time()
        window_start = now - window_seconds

        return self.redis.zcount(full_key, window_start, now)

    def is_blocked(self, key: str) -> bool:
        """Check if a key is in the blocklist."""
        if not self.redis:
            return False
        return self.redis.exists(f"{self.prefix}blocked:{key}") > 0

    def block(self, key: str, duration_seconds: int = 3600) -> None:
        """Add key to blocklist."""
        if not self.redis:
            return
        self.redis.setex(f"{self.prefix}blocked:{key}", duration_seconds, "1")

    def unblock(self, key: str) -> None:
        """Remove key from blocklist."""
        if not self.redis:
            return
        self.redis.delete(f"{self.prefix}blocked:{key}")
