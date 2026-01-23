import logging
from typing import TYPE_CHECKING, Optional
from .base import EventSink

if TYPE_CHECKING:
    from ..types import SecurityEvent

logger = logging.getLogger(__name__)


class MetricsSink(EventSink):
    """Exports events as metrics (Prometheus or StatsD)."""

    def __init__(self, backend: str = "prometheus"):
        self.backend = backend
        self._counters: dict = {}
        self._setup_backend()

    def _setup_backend(self):
        if self.backend == "prometheus":
            try:
                from prometheus_client import Counter
                self._event_counter = Counter(
                    "rail_security_events_total",
                    "Total security events",
                    ["event_type", "outcome", "severity"]
                )
                self._risk_counter = Counter(
                    "rail_security_risk_total",
                    "Accumulated risk scores",
                    ["event_type"]
                )
            except ImportError:
                logger.warning("prometheus_client not installed, metrics disabled")
                self._event_counter = None

    def write(self, event: "SecurityEvent") -> None:
        if self.backend == "prometheus" and getattr(self, "_event_counter", None):
            self._event_counter.labels(
                event_type=event.event_type.value,
                outcome=event.outcome.value,
                severity=event.severity.value,
            ).inc()

            if event.risk_score > 0:
                self._risk_counter.labels(
                    event_type=event.event_type.value
                ).inc(event.risk_score)
