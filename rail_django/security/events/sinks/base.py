from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..types import SecurityEvent


class EventSink(ABC):
    """Base class for event sinks."""

    @abstractmethod
    def write(self, event: "SecurityEvent") -> None:
        """Write event to the sink."""
        pass

    def flush(self) -> None:
        """Flush any buffered events."""
        pass

    def close(self) -> None:
        """Clean up resources."""
        pass
