import json
import logging
from typing import TYPE_CHECKING
from django.core.serializers.json import DjangoJSONEncoder
from .base import EventSink

if TYPE_CHECKING:
    from ..types import SecurityEvent


class FileSink(EventSink):
    """Writes events to Python logging (structured JSON)."""

    def __init__(self, logger_name: str = "security.audit"):
        self.logger = logging.getLogger(logger_name)

    def write(self, event: "SecurityEvent") -> None:
        log_data = event.to_dict()
        message = json.dumps(log_data, cls=DjangoJSONEncoder, ensure_ascii=False)

        level = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }.get(event.severity.value, logging.INFO)

        self.logger.log(level, message)
