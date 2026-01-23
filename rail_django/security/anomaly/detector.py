import logging
from dataclasses import dataclass
from typing import Optional
from django.conf import settings
from .backends.redis import RedisAnomalyBackend

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Result of anomaly detection check."""
    detected: bool
    reason: Optional[str] = None
    count: int = 0
    threshold: int = 0
    should_block: bool = False
    block_duration: int = 0


class AnomalyDetector:
    """
    Detects anomalous patterns like brute force attacks.

    Uses Redis for distributed counting across multiple processes/servers.
    """

    def __init__(self, backend: Optional[RedisAnomalyBackend] = None):
        self.backend = backend or RedisAnomalyBackend()
        self._load_config()

    def _load_config(self):
        thresholds = getattr(settings, "SECURITY_ANOMALY_THRESHOLDS", {})

        # Brute force thresholds
        self.login_failure_ip_threshold = thresholds.get("login_failure_per_ip", 10)
        self.login_failure_user_threshold = thresholds.get("login_failure_per_user", 5)
        self.login_failure_window = thresholds.get("login_failure_window", 300)  # 5 min

        # Rate limit thresholds
        self.rate_limit_threshold = thresholds.get("rate_limit_per_ip", 100)
        self.rate_limit_window = thresholds.get("rate_limit_window", 60)  # 1 min

        # Blocking config
        self.auto_block_enabled = thresholds.get("auto_block_enabled", True)
        self.block_duration = thresholds.get("block_duration", 3600)  # 1 hour

    def check_login_failure(
        self,
        client_ip: str,
        username: Optional[str] = None
    ) -> DetectionResult:
        """
        Check for brute force login attempts.

        Call this after each failed login attempt.
        """
        # Check if already blocked
        if self.backend.is_blocked(f"ip:{client_ip}"):
            return DetectionResult(
                detected=True,
                reason="ip_blocked",
                should_block=False  # Already blocked
            )

        # Check IP-based threshold
        ip_key = f"login_fail:ip:{client_ip}"
        ip_count, _ = self.backend.increment_counter(
            ip_key,
            window_seconds=self.login_failure_window
        )

        if ip_count >= self.login_failure_ip_threshold:
            if self.auto_block_enabled:
                self.backend.block(f"ip:{client_ip}", self.block_duration)
            return DetectionResult(
                detected=True,
                reason="ip_threshold_exceeded",
                count=ip_count,
                threshold=self.login_failure_ip_threshold,
                should_block=self.auto_block_enabled,
                block_duration=self.block_duration
            )

        # Check username-based threshold
        if username:
            if self.backend.is_blocked(f"user:{username}"):
                return DetectionResult(
                    detected=True,
                    reason="user_blocked"
                )

            user_key = f"login_fail:user:{username}"
            user_count, _ = self.backend.increment_counter(
                user_key,
                window_seconds=self.login_failure_window
            )

            if user_count >= self.login_failure_user_threshold:
                return DetectionResult(
                    detected=True,
                    reason="user_threshold_exceeded",
                    count=user_count,
                    threshold=self.login_failure_user_threshold,
                    should_block=False  # Don't auto-block users, just detect
                )

        return DetectionResult(detected=False, count=ip_count)

    def check_rate_limit(self, client_ip: str, endpoint: str = "global") -> DetectionResult:
        """
        Check request rate limit.

        Call this on each request.
        """
        if self.backend.is_blocked(f"ip:{client_ip}"):
            return DetectionResult(detected=True, reason="ip_blocked")

        key = f"rate:{endpoint}:{client_ip}"
        count, _ = self.backend.increment_counter(
            key,
            window_seconds=self.rate_limit_window
        )

        if count >= self.rate_limit_threshold:
            return DetectionResult(
                detected=True,
                reason="rate_limit_exceeded",
                count=count,
                threshold=self.rate_limit_threshold
            )

        return DetectionResult(detected=False, count=count)

    def is_ip_blocked(self, client_ip: str) -> bool:
        """Check if an IP is blocked."""
        return self.backend.is_blocked(f"ip:{client_ip}")

    def block_ip(self, client_ip: str, duration: Optional[int] = None) -> None:
        """Manually block an IP."""
        self.backend.block(f"ip:{client_ip}", duration or self.block_duration)

    def unblock_ip(self, client_ip: str) -> None:
        """Unblock an IP."""
        self.backend.unblock(f"ip:{client_ip}")


# Global detector instance
_detector: Optional[AnomalyDetector] = None


def get_anomaly_detector() -> AnomalyDetector:
    """Get the global anomaly detector."""
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector
