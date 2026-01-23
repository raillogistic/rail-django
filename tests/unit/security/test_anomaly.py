import pytest
from unittest.mock import Mock, patch
from rail_django.security.anomaly.detector import AnomalyDetector, DetectionResult
from rail_django.security.anomaly.backends.redis import RedisAnomalyBackend


class MockRedisBackend:
    def __init__(self):
        self.counters = {}
        self.blocked = set()

    def increment_counter(self, key, window_seconds=300, max_entries=1000):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key], False

    def get_counter(self, key, window_seconds=300):
        return self.counters.get(key, 0)

    def is_blocked(self, key):
        return key in self.blocked

    def block(self, key, duration_seconds=3600):
        self.blocked.add(key)

    def unblock(self, key):
        self.blocked.discard(key)


@pytest.mark.unit
class TestAnomalyDetector:
    def test_login_failure_below_threshold(self):
        backend = MockRedisBackend()
        detector = AnomalyDetector(backend=backend)
        detector.login_failure_ip_threshold = 10

        result = detector.check_login_failure("1.2.3.4")

        assert result.detected is False
        assert result.count == 1

    def test_login_failure_exceeds_threshold(self):
        backend = MockRedisBackend()
        detector = AnomalyDetector(backend=backend)
        detector.login_failure_ip_threshold = 3
        detector.auto_block_enabled = True

        # Simulate multiple failures
        for _ in range(2):
            detector.check_login_failure("1.2.3.4")

        result = detector.check_login_failure("1.2.3.4")

        assert result.detected is True
        assert result.reason == "ip_threshold_exceeded"
        assert result.should_block is True

    def test_blocked_ip_detected(self):
        backend = MockRedisBackend()
        backend.blocked.add("ip:1.2.3.4")
        detector = AnomalyDetector(backend=backend)

        result = detector.check_login_failure("1.2.3.4")

        assert result.detected is True
        assert result.reason == "ip_blocked"

    def test_user_threshold_separate_from_ip(self):
        backend = MockRedisBackend()
        detector = AnomalyDetector(backend=backend)
        detector.login_failure_ip_threshold = 100  # High IP threshold
        detector.login_failure_user_threshold = 3  # Low user threshold

        for _ in range(3):
            detector.check_login_failure("1.2.3.4", username="admin")

        result = detector.check_login_failure("5.6.7.8", username="admin")

        assert result.detected is True
        assert result.reason == "user_threshold_exceeded"
