import logging
import queue
import threading
from typing import List, Optional
from django.conf import settings
from .types import SecurityEvent
from .sinks.base import EventSink

logger = logging.getLogger(__name__)


class EventBus:
    """
    Async event dispatcher with pluggable sinks.

    Events are queued and processed by a background thread to avoid
    blocking request handling.
    """

    def __init__(self, async_processing: bool = True, max_queue_size: int = 10000):
        self._sinks: List[EventSink] = []
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._async = async_processing
        self._running = False
        self._worker: Optional[threading.Thread] = None
        self._redactor: Optional["EventRedactor"] = None

    def add_sink(self, sink: EventSink) -> "EventBus":
        """Add a sink to receive events."""
        self._sinks.append(sink)
        return self

    def set_redactor(self, redactor: "EventRedactor") -> "EventBus":
        """Set the redactor for sensitive data."""
        self._redactor = redactor
        return self

    def start(self) -> None:
        """Start the background processing thread."""
        if self._async and not self._running:
            self._running = True
            self._worker = threading.Thread(target=self._process_loop, daemon=True)
            self._worker.start()
            logger.info("EventBus started with async processing")

    def stop(self) -> None:
        """Stop processing and flush remaining events."""
        self._running = False
        if self._worker:
            self._worker.join(timeout=5.0)
        self._flush_queue()
        for sink in self._sinks:
            sink.close()

    def emit(self, event: SecurityEvent) -> None:
        """Emit an event to all sinks."""
        # Redact sensitive data
        if self._redactor:
            event = self._redactor.redact(event)

        if self._async:
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                logger.warning("Event queue full, dropping event")
        else:
            self._dispatch(event)

    def _process_loop(self) -> None:
        """Background thread processing loop."""
        while self._running:
            try:
                event = self._queue.get(timeout=1.0)
                self._dispatch(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}")

    def _dispatch(self, event: SecurityEvent) -> None:
        """Send event to all sinks."""
        for sink in self._sinks:
            try:
                sink.write(event)
            except Exception as e:
                logger.error(f"Sink {sink.__class__.__name__} failed: {e}")

    def _flush_queue(self) -> None:
        """Process remaining events in queue."""
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                self._dispatch(event)
            except queue.Empty:
                break


class EventRedactor:
    """Redacts sensitive data from events before storage."""

    def __init__(self, fields: Optional[List[str]] = None, mask: str = "***REDACTED***"):
        self.fields = set(f.lower() for f in (fields or [
            "password", "token", "secret", "key", "credential",
            "authorization", "ssn", "credit_card", "cvv",
        ]))
        self.mask = mask

    def redact(self, event: SecurityEvent) -> SecurityEvent:
        """Return a new event with sensitive data redacted."""
        import copy
        event = copy.deepcopy(event)
        event.context = self._redact_dict(event.context)
        if event.error_message:
            event.error_message = self._redact_string(event.error_message)
        return event

    def _redact_dict(self, data: dict) -> dict:
        result = {}
        for key, value in data.items():
            if key.lower() in self.fields:
                result[key] = self.mask
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self._redact_dict(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def _redact_string(self, text: str) -> str:
        lowered = text.lower()
        for field in self.fields:
            if field in lowered:
                return self.mask
        return text


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = _create_event_bus()
    return _event_bus


def _create_event_bus() -> EventBus:
    """Create and configure the event bus from settings."""
    from .sinks.database import DatabaseSink
    from .sinks.file import FileSink
    from .sinks.webhook import WebhookSink

    async_mode = getattr(settings, "SECURITY_EVENT_ASYNC", True)
    bus = EventBus(async_processing=async_mode)

    # Configure redactor
    redaction_fields = getattr(settings, "AUDIT_REDACTION_FIELDS", None)
    bus.set_redactor(EventRedactor(fields=redaction_fields))

    # Add database sink
    if getattr(settings, "AUDIT_STORE_IN_DATABASE", True):
        bus.add_sink(DatabaseSink())

    # Add file sink
    if getattr(settings, "AUDIT_STORE_IN_FILE", True):
        bus.add_sink(FileSink())

    # Add webhook sink
    webhook_url = getattr(settings, "AUDIT_WEBHOOK_URL", None)
    if webhook_url:
        bus.add_sink(WebhookSink(url=webhook_url))

    # Add metrics sink
    if getattr(settings, "SECURITY_METRICS_ENABLED", False):
        from .sinks.metrics import MetricsSink
        bus.add_sink(MetricsSink())

    bus.start()
    return bus
