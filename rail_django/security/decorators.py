import functools
from typing import Optional, Callable, Any
from .events.types import EventType, Outcome
from .api import security


def audit(
    event_type: EventType,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    include_args: bool = False
) -> Callable:
    """
    Decorator to automatically log function calls.

    Usage:
        @audit(EventType.DATA_READ, resource_type="model")
        def get_user(self, info, id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Try to find request in args (common patterns)
            request = None
            info = kwargs.get("info") or (args[1] if len(args) > 1 else None)
            if hasattr(info, "context"):
                request = getattr(info.context, "request", None)

            context = {}
            if include_args:
                context["args"] = {k: v for k, v in kwargs.items() if k != "info"}

            try:
                result = func(*args, **kwargs)
                security.emit(
                    event_type,
                    request=request,
                    outcome=Outcome.SUCCESS,
                    action=action or func.__name__,
                    resource_type=resource_type,
                    resource_name=func.__name__,
                    context=context
                )
                return result
            except Exception as e:
                security.emit(
                    event_type,
                    request=request,
                    outcome=Outcome.ERROR,
                    action=action or func.__name__,
                    resource_type=resource_type,
                    resource_name=func.__name__,
                    context=context,
                    error=str(e)
                )
                raise

        return wrapper
    return decorator
