"""
Audit decorators.
"""

from functools import wraps
from django.db import models, transaction
from django.utils import timezone as django_timezone
from graphql import GraphQLError
from .types import AuditEvent, AuditEventType, AuditSeverity
from .utils import (
    _resolve_request,
    _resolve_user,
    _snapshot_instance_fields,
    _classify_exception,
    get_client_ip,
    hash_query,
)
from .logger import audit_logger


def audit_graphql_operation(operation_type: str = None):
    """Decorator to audit GraphQL operations."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            info = next((arg for arg in args if hasattr(arg, "context")), None)
            if not info: return func(*args, **kwargs)
            ctx = info.context
            req = _resolve_request(ctx)
            user = _resolve_user(ctx, req)
            op_val = getattr(info.operation, "operation", None).value if info.operation and getattr(info.operation, "operation", None) else None
            gql_op_name = getattr(info.operation.name, "value", None) if info.operation and getattr(info.operation, "name", None) else None
            details = {"schema_name": getattr(ctx, "schema_name", None), "operation_name": gql_op_name, "request_path": getattr(req, "path", None), "request_method": getattr(req, "method", None)}
            event = AuditEvent(event_type=AuditEventType.DATA_ACCESS, severity=AuditSeverity.INFO, timestamp=django_timezone.now(), user_id=user.id if user and user.is_authenticated else None, username=user.username if user and user.is_authenticated else None, ip_address=get_client_ip(req) if req else None, user_agent=req.META.get("HTTP_USER_AGENT") if req else None, session_id=getattr(req.session, "session_key", None) if req and hasattr(req, "session") else None, operation_name=info.field_name, operation_type=operation_type or op_val, query_hash=hash_query(info.operation) if info.operation else None, variables=info.variable_values, details={k:v for k,v in details.items() if v} or None)
            try:
                res = func(*args, **kwargs); audit_logger.log_event(event); return res
            except Exception as e:
                event.event_type, event.severity = _classify_exception(e); event.message = str(e)
                if isinstance(e, GraphQLError):
                    code = (getattr(e, "extensions", {}) or {}).get("code")
                    if code: event.details = dict(event.details or {}); event.details["error_code"] = str(code)
                event.details = dict(event.details or {}); event.details["error_type"] = e.__class__.__name__
                audit_logger.log_event(event); raise
        return wrapper
    return decorator


def audit_data_modification(model_class: type, operation: str):
    """Decorator to audit data modifications."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            info = next((arg for arg in args if hasattr(arg, "context")), None)
            instance = next((arg for arg in args if isinstance(arg, model_class)), None)
            ctx = info.context if info else None
            req = _resolve_request(ctx)
            user = _resolve_user(ctx, req)
            old_vals = _snapshot_instance_fields(instance) if instance and operation in ["update", "delete"] else None
            try:
                res = func(*args, **kwargs)
                if instance is None and isinstance(res, model_class): instance = res
                new_vals = _snapshot_instance_fields(instance) if instance and operation in ["create", "update"] else None
                details = {"operation": operation, "model": model_class.__name__, "schema_name": getattr(ctx, "schema_name", None), "request_path": getattr(req, "path", None), "request_method": getattr(req, "method", None)}
                event = AuditEvent(event_type={"create": AuditEventType.CREATE, "update": AuditEventType.UPDATE, "delete": AuditEventType.DELETE}.get(operation, AuditEventType.DATA_ACCESS), severity=AuditSeverity.INFO, timestamp=django_timezone.now(), user_id=user.id if user and user.is_authenticated else None, username=user.username if user and user.is_authenticated else None, ip_address=get_client_ip(req) if req else None, user_agent=req.META.get("HTTP_USER_AGENT") if req else None, session_id=getattr(req.session, "session_key", None) if req and hasattr(req, "session") else None, model_name=model_class.__name__, object_id=str(instance.pk) if instance and hasattr(instance, "pk") else None, old_value=old_vals, new_value=new_vals, details={k:v for k,v in details.items() if v})
                audit_logger.log_event(event); return res
            except Exception as e:
                etype, sev = _classify_exception(e)
                edetails = {"operation": operation, "error": str(e), "error_type": e.__class__.__name__, "schema_name": getattr(ctx, "schema_name", None), "request_path": getattr(req, "path", None), "request_method": getattr(req, "method", None)}
                event = AuditEvent(event_type=etype, severity=sev, timestamp=django_timezone.now(), user_id=user.id if user and user.is_authenticated else None, username=user.username if user and user.is_authenticated else None, ip_address=get_client_ip(req) if req else None, user_agent=req.META.get("HTTP_USER_AGENT") if req else None, session_id=getattr(req.session, "session_key", None) if req and hasattr(req, "session") else None, model_name=model_class.__name__, message=f"Error during {operation}: {str(e)}", details={k:v for k,v in edetails.items() if v})
                try:
                    if not transaction.get_connection().needs_rollback: audit_logger.log_event(event)
                except Exception: pass
                raise
        return wrapper
    return decorator
