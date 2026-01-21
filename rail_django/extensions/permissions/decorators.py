"""
Permission decorators.
"""

import logging
from functools import wraps
from django.db import models
from django.core.exceptions import PermissionDenied
from .base import BasePermissionChecker, PermissionLevel

logger = logging.getLogger(__name__)


def require_permission(checker: BasePermissionChecker, level: PermissionLevel = PermissionLevel.OPERATION):
    """Decorator for exiger des permissions."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, info, *args, **kwargs):
            user = getattr(info.context, "user", None)
            def _extract_object_instance(args, kwargs):
                for key in ("instance", "obj", "object"):
                    if key in kwargs and kwargs[key] is not None: return kwargs[key]
                for arg in args:
                    if isinstance(arg, models.Model): return arg
                return None
            def _extract_object_id(kwargs):
                for key in ("object_id", "id", "pk"):
                    if key in kwargs and kwargs[key] is not None: return kwargs[key]
                input_value = kwargs.get("input") or kwargs.get("data")
                if isinstance(input_value, dict):
                    for key in ("object_id", "id", "pk"):
                        if key in input_value and input_value[key] is not None: return input_value[key]
                elif input_value is not None:
                    for key in ("object_id", "id", "pk"):
                        if hasattr(input_value, key):
                            val = getattr(input_value, key)
                            if val is not None: return val
                return None
            def _resolve_instance(model_class, object_id):
                if object_id is None: return None
                try: return model_class.objects.get(pk=object_id)
                except Exception:
                    try:
                        from graphql_relay import from_global_id
                        _, decoded_id = from_global_id(str(object_id))
                        return model_class.objects.get(pk=decoded_id)
                    except Exception: return None

            obj = _extract_object_instance(args, kwargs)
            model_class = getattr(self, "model_class", None)
            if obj is None and model_class is not None:
                obj = _resolve_instance(model_class, _extract_object_id(kwargs))

            result = checker.check_permission(user, obj)
            if not result.allowed:
                logger.warning(f"Permission refusÇ¸e: {result.reason}")
                raise PermissionDenied(result.reason)
            return func(self, info, *args, **kwargs)
        return wrapper
    return decorator


def require_authentication(func):
    """Decorator for requiring authentication."""
    @wraps(func)
    def wrapper(self, info, *args, **kwargs):
        user = getattr(info.context, "user", None)
        if not user or not user.is_authenticated: raise PermissionDenied("Authentification requise")
        return func(self, info, *args, **kwargs)
    return wrapper


def require_superuser(func):
    """Decorator for requiring superuser rights."""
    @wraps(func)
    def wrapper(self, info, *args, **kwargs):
        user = getattr(info.context, "user", None)
        if not user or not user.is_superuser: raise PermissionDenied("Droits de superutilisateur requis")
        return func(self, info, *args, **kwargs)
    return wrapper
