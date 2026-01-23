import json
import logging
from typing import TYPE_CHECKING, Optional
from django.core.serializers.json import DjangoJSONEncoder
from .base import EventSink

if TYPE_CHECKING:
    from ..types import SecurityEvent

logger = logging.getLogger(__name__)


class WebhookSink(EventSink):
    """Sends events to external webhook."""

    def __init__(
        self,
        url: str,
        timeout: int = 5,
        headers: Optional[dict] = None,
        min_severity: str = "warning"
    ):
        self.url = url
        self.timeout = timeout
        self.headers = headers or {"Content-Type": "application/json"}
        self.min_severity = min_severity
        self._severity_order = ["debug", "info", "warning", "error", "critical"]

    def _should_send(self, event: "SecurityEvent") -> bool:
        try:
            event_level = self._severity_order.index(event.severity.value)
            min_level = self._severity_order.index(self.min_severity)
            return event_level >= min_level
        except ValueError:
            return True  # Default to sending if severity not found

    def write(self, event: "SecurityEvent") -> None:
        if not self._should_send(event):
            return

        try:
            import requests
            response = requests.post(
                self.url,
                data=json.dumps(event.to_dict(), cls=DjangoJSONEncoder),
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except ImportError:
            logger.warning("requests library not installed, webhook disabled")
        except Exception as e:
            logger.warning(f"Failed to send event to webhook: {e}")
