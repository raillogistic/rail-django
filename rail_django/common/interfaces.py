"""
Common interfaces and protocols for Rail Django.
"""

from typing import Any, Callable, Optional, Protocol

class RateLimiterProtocol(Protocol):
    def check(
        self,
        context: str,
        request: Any = None,
        *,
        user: Any = None,
        ip: Optional[str] = None,
        cost: int = 1,
    ) -> Any:
        ...


class QueryOptimizerProtocol(Protocol):
    def optimize_queryset(self, queryset: Any, info: Any = None) -> Any:
        ...


class AuditLoggerProtocol(Protocol):
    def log_event(self, event: Any) -> None:
        ...

class QueryCacheBackendProtocol(Protocol):
    def get(self, key: str) -> Any:
        ...

    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        ...

    def get_version(self, namespace: str) -> str:
        ...

    def bump_version(self, namespace: str) -> str:
        ...
