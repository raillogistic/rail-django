"""
Protected audit views for accessing logs and security information.

These views are protected and require authentication + admin privileges.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..extensions.audit.models import get_audit_event_model
from ..security.events.types import EventType, Severity

logger = logging.getLogger(__name__)


def require_audit_access(view_func):
    """
    Decorator that requires authentication and admin/superuser privileges.
    Returns 401 for unauthenticated, 403 for unauthorized.
    """

    def wrapper(request: HttpRequest, *args, **kwargs):
        user = getattr(request, "user", None)

        # Check authentication
        if not user or not getattr(user, "is_authenticated", False):
            # Check if this is an API request or HTML request
            if request.headers.get("Accept", "").find("application/json") != -1:
                return JsonResponse(
                    {"error": "Authentication required", "code": "UNAUTHENTICATED"},
                    status=401,
                )
            # For HTML requests, redirect to login or show error page
            return HttpResponse(
                """
                <!DOCTYPE html>
                <html>
                <head><title>Authentication Required</title></head>
                <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #1e3a5f;">
                    <div style="text-align: center; color: #fff;">
                        <h1>Authentication Required</h1>
                        <p>Please log in to access the audit dashboard.</p>
                        <a href="/admin/login/?next=/audit/dashboard/" style="color: #00d4ff;">Go to Login</a>
                    </div>
                </body>
                </html>
                """,
                status=401,
            )

        # Check authorization - require superuser or staff
        is_superuser = getattr(user, "is_superuser", False)
        is_staff = getattr(user, "is_staff", False)

        # Also check for custom audit permission via RBAC
        has_audit_permission = False
        if hasattr(user, "has_perm"):
            has_audit_permission = user.has_perm("rail_django.view_auditeventmodel")

        if not (is_superuser or is_staff or has_audit_permission):
            if request.headers.get("Accept", "").find("application/json") != -1:
                return JsonResponse(
                    {
                        "error": "Admin privileges required to access audit logs",
                        "code": "FORBIDDEN",
                    },
                    status=403,
                )
            return HttpResponse(
                """
                <!DOCTYPE html>
                <html>
                <head><title>Access Denied</title></head>
                <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #1e3a5f;">
                    <div style="text-align: center; color: #fff;">
                        <h1>Access Denied</h1>
                        <p>You do not have permission to access the audit dashboard.</p>
                        <p style="color: #a0a0a0;">Admin or staff privileges are required.</p>
                    </div>
                </body>
                </html>
                """,
                status=403,
            )

        return view_func(request, *args, **kwargs)

    return wrapper


class AuditDashboardView(View):
    """
    Protected view for the audit dashboard HTML interface.

    Serves the beautiful HTML/CSS/JS dashboard for viewing audit logs
    and security information.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the audit dashboard."""
        user = getattr(request, "user", None)

        # Check authentication
        if not user or not getattr(user, "is_authenticated", False):
            return HttpResponse(
                """
                <!DOCTYPE html>
                <html>
                <head><title>Authentication Required</title></head>
                <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #1e3a5f;">
                    <div style="text-align: center; color: #fff;">
                        <h1>Authentication Required</h1>
                        <p>Please log in to access the audit dashboard.</p>
                        <a href="/admin/login/?next=/audit/dashboard/" style="color: #00d4ff;">Go to Login</a>
                    </div>
                </body>
                </html>
                """,
                status=401,
            )

        # Check authorization
        is_superuser = getattr(user, "is_superuser", False)
        is_staff = getattr(user, "is_staff", False)
        has_audit_permission = False
        if hasattr(user, "has_perm"):
            has_audit_permission = user.has_perm("rail_django.view_auditeventmodel")

        if not (is_superuser or is_staff or has_audit_permission):
            return HttpResponse(
                """
                <!DOCTYPE html>
                <html>
                <head><title>Access Denied</title></head>
                <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #1e3a5f;">
                    <div style="text-align: center; color: #fff;">
                        <h1>Access Denied</h1>
                        <p>You do not have permission to access the audit dashboard.</p>
                        <p style="color: #a0a0a0;">Admin or staff privileges are required.</p>
                    </div>
                </body>
                </html>
                """,
                status=403,
            )

        return render(request, "audit_dashboard.html")


class AuditAPIView(View):
    """
    Protected API endpoint for accessing audit logs with rich filtering.
    """

    @method_decorator(csrf_exempt)
    @method_decorator(require_audit_access)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Retrieve audit events with filtering and pagination.
        """
        try:
            AuditModel = get_audit_event_model()
            queryset = AuditModel.objects.all()

            # Apply filters
            queryset = self._apply_filters(request, queryset)

            # Get total count before pagination
            total_count = queryset.count()

            # Apply ordering
            order_by = request.GET.get("order_by", "-timestamp")
            allowed_order_fields = {
                "timestamp",
                "-timestamp",
                "event_type",
                "-event_type",
                "severity",
                "-severity",
                "user_id",
                "-user_id",
            }
            if order_by in allowed_order_fields:
                queryset = queryset.order_by(order_by)
            else:
                queryset = queryset.order_by("-timestamp")

            # Apply pagination
            page = max(1, int(request.GET.get("page", 1)))
            page_size = min(500, max(1, int(request.GET.get("page_size", 50))))
            offset = (page - 1) * page_size
            queryset = queryset[offset : offset + page_size]

            # Serialize events
            events = [self._serialize_event(event) for event in queryset]

            return JsonResponse(
                {
                    "events": events,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total_count": total_count,
                        "total_pages": (total_count + page_size - 1) // page_size,
                        "has_next": offset + page_size < total_count,
                        "has_previous": page > 1,
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except ValueError as e:
            return JsonResponse(
                {"error": f"Invalid parameter: {e}", "code": "INVALID_PARAMETER"},
                status=400,
            )
        except Exception as e:
            logger.error(f"Error retrieving audit events: {e}")
            return JsonResponse(
                {"error": "Internal server error", "code": "INTERNAL_ERROR"},
                status=500,
            )

    def _apply_filters(self, request: HttpRequest, queryset):
        """Apply query parameter filters to the queryset."""
        # Filter by event_type
        event_type = request.GET.get("event_type")
        if event_type:
            queryset = queryset.filter(event_type=event_type)

        # Filter by severity
        severity = request.GET.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)

        # Filter by user_id
        user_id = request.GET.get("user_id")
        if user_id:
            queryset = queryset.filter(user_id=int(user_id))

        # Filter by username (partial match)
        username = request.GET.get("username")
        if username:
            queryset = queryset.filter(username__icontains=username)

        # Filter by client_ip
        client_ip = request.GET.get("client_ip")
        if client_ip:
            queryset = queryset.filter(client_ip=client_ip)

        # Filter by correlation_id (in additional_data)
        correlation_id = request.GET.get("correlation_id")
        if correlation_id:
            queryset = queryset.filter(additional_data__correlation_id=correlation_id)

        # Filter by outcome (in additional_data)
        outcome = request.GET.get("outcome")
        if outcome:
            queryset = queryset.filter(additional_data__outcome=outcome)

        # Filter by date range
        date_from = request.GET.get("date_from")
        if date_from:
            try:
                from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                queryset = queryset.filter(timestamp__gte=from_dt)
            except ValueError:
                pass

        date_to = request.GET.get("date_to")
        if date_to:
            try:
                to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                queryset = queryset.filter(timestamp__lte=to_dt)
            except ValueError:
                pass

        # Filter by hours (last N hours)
        hours = request.GET.get("hours")
        if hours:
            try:
                since = datetime.now(timezone.utc) - timedelta(hours=int(hours))
                queryset = queryset.filter(timestamp__gte=since)
            except ValueError:
                pass

        # Full-text search
        search = request.GET.get("search")
        if search:
            queryset = queryset.filter(
                Q(additional_data__icontains=search)
                | Q(error_message__icontains=search)
                | Q(request_path__icontains=search)
            )

        return queryset

    def _serialize_event(self, event) -> dict[str, Any]:
        """Serialize an audit event to a dictionary."""
        additional_data = event.additional_data or {}
        if not isinstance(additional_data, dict):
            additional_data = {}

        return {
            "id": event.id,
            "event_type": event.event_type,
            "severity": event.severity,
            "user_id": event.user_id,
            "username": event.username,
            "client_ip": event.client_ip,
            "user_agent": event.user_agent,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "request_path": event.request_path,
            "request_method": event.request_method,
            "correlation_id": additional_data.get("correlation_id"),
            "outcome": additional_data.get("outcome"),
            "action": additional_data.get("action"),
            "resource": additional_data.get("resource"),
            "risk_score": additional_data.get("risk_score", 0),
            "context": additional_data.get("context"),
            "error_message": event.error_message,
        }


class AuditStatsView(View):
    """
    Protected API endpoint for audit statistics and aggregations.
    """

    @method_decorator(csrf_exempt)
    @method_decorator(require_audit_access)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Get audit statistics for the specified period.
        """
        try:
            hours = int(request.GET.get("hours", 24))
            since = datetime.now(timezone.utc) - timedelta(hours=hours)

            AuditModel = get_audit_event_model()
            queryset = AuditModel.objects.filter(timestamp__gte=since)

            # Get counts by event type
            event_type_counts = dict(
                queryset.values("event_type")
                .annotate(count=Count("id"))
                .values_list("event_type", "count")
            )

            # Get counts by severity
            severity_counts = dict(
                queryset.values("severity")
                .annotate(count=Count("id"))
                .values_list("severity", "count")
            )

            # Top IPs with high risk events
            top_risky_ips = list(
                queryset.filter(additional_data__risk_score__gte=50)
                .values("client_ip")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )

            # Top users by event count
            top_users = list(
                queryset.filter(username__isnull=False)
                .values("username")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )

            # Recent high severity events
            high_severity_count = queryset.filter(
                severity__in=[Severity.ERROR.value, Severity.CRITICAL.value]
            ).count()

            return JsonResponse(
                {
                    "period_hours": hours,
                    "total_events": queryset.count(),
                    "by_event_type": event_type_counts,
                    "by_severity": severity_counts,
                    "top_risky_ips": top_risky_ips,
                    "top_users": top_users,
                    "high_severity_count": high_severity_count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except Exception as e:
            logger.error(f"Error generating audit stats: {e}")
            return JsonResponse(
                {"error": "Internal server error", "code": "INTERNAL_ERROR"},
                status=500,
            )


class SecurityReportView(View):
    """
    Protected API endpoint for security reports.
    """

    @method_decorator(csrf_exempt)
    @method_decorator(require_audit_access)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Generate a security report for the specified period.
        """
        try:
            hours = int(request.GET.get("hours", 24))
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            AuditModel = get_audit_event_model()
            queryset = AuditModel.objects.filter(timestamp__gte=since)

            # Detect potential brute force attempts (failed logins)
            brute_force_suspects = list(
                queryset.filter(event_type=EventType.AUTH_LOGIN_FAILURE.value)
                .values("client_ip")
                .annotate(attempts=Count("id"))
                .filter(attempts__gte=5)
                .order_by("-attempts")[:20]
            )

            # Detect blocked queries
            blocked_queries = list(
                queryset.filter(event_type__startswith="query.blocked")
                .values("event_type", "client_ip", "timestamp")
                .order_by("-timestamp")[:20]
            )

            # Get rate limited requests
            rate_limited = list(
                queryset.filter(event_type=EventType.RATE_LIMIT_EXCEEDED.value)
                .values("client_ip")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )

            # Timeline of high severity events
            high_severity_timeline = list(
                queryset.filter(severity__in=[Severity.ERROR.value, Severity.CRITICAL.value])
                .order_by("-timestamp")
                .values(
                    "event_type",
                    "severity",
                    "client_ip",
                    "username",
                    "timestamp",
                )[:50]
            )

            # Format timestamps
            for event in high_severity_timeline:
                if event.get("timestamp"):
                    event["timestamp"] = event["timestamp"].isoformat()

            for event in blocked_queries:
                if event.get("timestamp"):
                    event["timestamp"] = event["timestamp"].isoformat()

            report = {
                "period_hours": hours,
                "brute_force_suspects": brute_force_suspects,
                "blocked_queries": blocked_queries,
                "rate_limited_ips": rate_limited,
                "high_severity_timeline": high_severity_timeline,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            return JsonResponse(report)

        except Exception as e:
            logger.error(f"Error generating security report: {e}")
            return JsonResponse(
                {"error": "Internal server error", "code": "INTERNAL_ERROR"},
                status=500,
            )


class AuditEventDetailView(View):
    """
    Protected API endpoint for viewing a single audit event.
    """

    @method_decorator(csrf_exempt)
    @method_decorator(require_audit_access)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request: HttpRequest, event_id: int) -> JsonResponse:
        """
        Retrieve a single audit event by ID.
        """
        try:
            AuditModel = get_audit_event_model()
            event = AuditModel.objects.filter(id=event_id).first()

            if not event:
                return JsonResponse(
                    {"error": "Audit event not found", "code": "NOT_FOUND"},
                    status=404,
                )

            return JsonResponse(
                {
                    "event": {
                        "id": event.id,
                        "event_type": event.event_type,
                        "severity": event.severity,
                        "user_id": event.user_id,
                        "username": event.username,
                        "client_ip": event.client_ip,
                        "user_agent": event.user_agent,
                        "timestamp": (
                            event.timestamp.isoformat() if event.timestamp else None
                        ),
                        "request_path": event.request_path,
                        "request_method": event.request_method,
                        "additional_data": event.additional_data,
                        "session_id": event.session_id,
                        "success": event.success,
                        "error_message": event.error_message,
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except Exception as e:
            logger.error(f"Error retrieving audit event: {e}")
            return JsonResponse(
                {"error": "Internal server error", "code": "INTERNAL_ERROR"},
                status=500,
            )


class AuditEventTypesView(View):
    """
    Protected API endpoint for listing available event types and severities.
    """

    @method_decorator(csrf_exempt)
    @method_decorator(require_audit_access)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        List all available event types and severities.
        """
        return JsonResponse(
            {
                "event_types": [e.value for e in EventType],
                "severities": [s.value for s in Severity],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


def get_audit_urls():
    """
    Return URL patterns for audit views.

    Returns:
        List: Django URL patterns
    """
    from django.urls import path

    return [
        path("audit/dashboard/", AuditDashboardView.as_view(), name="audit_dashboard"),
        path("audit/", AuditAPIView.as_view(), name="audit_api"),
        path("audit/stats/", AuditStatsView.as_view(), name="audit_stats"),
        path("audit/security-report/", SecurityReportView.as_view(), name="audit_security_report"),
        path("audit/event/<int:event_id>/", AuditEventDetailView.as_view(), name="audit_event_detail"),
        path("audit/meta/", AuditEventTypesView.as_view(), name="audit_event_types"),
    ]
