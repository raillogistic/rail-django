"""
Protected audit views for accessing logs and security information.

These views are protected and require authentication + admin privileges.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count, Q
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..extensions.audit.models import get_audit_event_model
from ..extensions.audit.logger import audit_logger

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
            return JsonResponse(
                {"error": "Authentication required", "code": "UNAUTHENTICATED"},
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
            return JsonResponse(
                {
                    "error": "Admin privileges required to access audit logs",
                    "code": "FORBIDDEN",
                },
                status=403,
            )

        return view_func(request, *args, **kwargs)

    return wrapper


class AuditAPIView(View):
    """
    Protected API endpoint for accessing audit logs with rich filtering.

    Supports filtering by:
    - event_type: Filter by event type (login_success, login_failure, etc.)
    - severity: Filter by severity level (low, medium, high, critical)
    - user_id: Filter by user ID
    - username: Filter by username (partial match)
    - client_ip: Filter by client IP address
    - success: Filter by success status (true/false)
    - date_from: Filter events from this date (ISO format)
    - date_to: Filter events until this date (ISO format)
    - hours: Filter events from the last N hours
    - search: Full-text search in additional_data
    - page: Page number (default: 1)
    - page_size: Number of items per page (default: 50, max: 500)
    - order_by: Field to order by (default: -timestamp)
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

        # Filter by multiple event types
        event_types = request.GET.getlist("event_types")
        if event_types:
            queryset = queryset.filter(event_type__in=event_types)

        # Filter by severity
        severity = request.GET.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)

        # Filter by multiple severities
        severities = request.GET.getlist("severities")
        if severities:
            queryset = queryset.filter(severity__in=severities)

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

        # Filter by success status
        success = request.GET.get("success")
        if success is not None and success.lower() in ("true", "false"):
            queryset = queryset.filter(success=success.lower() == "true")

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

        # Filter by request_path (partial match)
        request_path = request.GET.get("request_path")
        if request_path:
            queryset = queryset.filter(request_path__icontains=request_path)

        # Filter by session_id
        session_id = request.GET.get("session_id")
        if session_id:
            queryset = queryset.filter(session_id=session_id)

        # Full-text search in additional_data (JSON field)
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
            "additional_data": event.additional_data,
            "session_id": event.session_id,
            "success": event.success,
            "error_message": event.error_message,
        }


class AuditStatsView(View):
    """
    Protected API endpoint for audit statistics and aggregations.

    Provides summary statistics for the specified time period.
    """

    @method_decorator(csrf_exempt)
    @method_decorator(require_audit_access)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Get audit statistics for the specified period.

        Query parameters:
        - hours: Time period in hours (default: 24)
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

            # Get counts by success/failure
            success_counts = dict(
                queryset.values("success")
                .annotate(count=Count("id"))
                .values_list("success", "count")
            )

            # Top IPs with failed events
            top_failed_ips = list(
                queryset.filter(success=False)
                .values("client_ip")
                .annotate(count=Count("client_ip"))
                .order_by("-count")[:10]
            )

            # Top users by event count
            top_users = list(
                queryset.filter(username__isnull=False)
                .values("username", "user_id")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )

            # Top event types
            top_event_types = list(
                queryset.values("event_type")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )

            # Recent high severity events
            high_severity_count = queryset.filter(
                severity__in=["high", "critical"]
            ).count()

            return JsonResponse(
                {
                    "period_hours": hours,
                    "total_events": queryset.count(),
                    "by_event_type": event_type_counts,
                    "by_severity": severity_counts,
                    "by_success": {
                        "successful": success_counts.get(True, 0),
                        "failed": success_counts.get(False, 0),
                    },
                    "top_failed_ips": top_failed_ips,
                    "top_users": top_users,
                    "top_event_types": top_event_types,
                    "high_severity_count": high_severity_count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except ValueError as e:
            return JsonResponse(
                {"error": f"Invalid parameter: {e}", "code": "INVALID_PARAMETER"},
                status=400,
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

    Generates comprehensive security reports with threat analysis.
    """

    @method_decorator(csrf_exempt)
    @method_decorator(require_audit_access)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Generate a security report for the specified period.

        Query parameters:
        - hours: Time period in hours (default: 24)
        """
        try:
            hours = int(request.GET.get("hours", 24))

            # Use the audit_logger's built-in security report
            report = audit_logger.get_security_report(hours=hours)

            if "error" in report:
                return JsonResponse(
                    {"error": report["error"], "code": "REPORT_ERROR"},
                    status=500,
                )

            # Add additional security metrics
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            AuditModel = get_audit_event_model()
            queryset = AuditModel.objects.filter(timestamp__gte=since)

            # Detect potential brute force attempts
            brute_force_suspects = list(
                queryset.filter(event_type="login_failure")
                .values("client_ip")
                .annotate(attempts=Count("id"))
                .filter(attempts__gte=5)
                .order_by("-attempts")[:20]
            )

            # Detect suspicious activity patterns
            suspicious_events = list(
                queryset.filter(event_type="suspicious_activity")
                .values("client_ip", "username", "timestamp", "additional_data")
                .order_by("-timestamp")[:20]
            )

            # Get rate limited requests
            rate_limited = list(
                queryset.filter(event_type="rate_limited")
                .values("client_ip")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )

            # Timeline of high severity events
            high_severity_timeline = list(
                queryset.filter(severity__in=["high", "critical"])
                .order_by("-timestamp")
                .values(
                    "event_type",
                    "severity",
                    "client_ip",
                    "username",
                    "timestamp",
                    "success",
                )[:50]
            )

            # Format timeline timestamps
            for event in high_severity_timeline:
                if event.get("timestamp"):
                    event["timestamp"] = event["timestamp"].isoformat()

            # Format suspicious events timestamps
            for event in suspicious_events:
                if event.get("timestamp"):
                    event["timestamp"] = event["timestamp"].isoformat()

            report.update(
                {
                    "brute_force_suspects": brute_force_suspects,
                    "suspicious_events": suspicious_events,
                    "rate_limited_ips": rate_limited,
                    "high_severity_timeline": high_severity_timeline,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            return JsonResponse(report)

        except ValueError as e:
            return JsonResponse(
                {"error": f"Invalid parameter: {e}", "code": "INVALID_PARAMETER"},
                status=400,
            )
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
        from ..extensions.audit.types import AuditEventType, AuditSeverity

        return JsonResponse(
            {
                "event_types": [e.value for e in AuditEventType],
                "severities": [s.value for s in AuditSeverity],
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
        path("audit/", AuditAPIView.as_view(), name="audit_api"),
        path("audit/stats/", AuditStatsView.as_view(), name="audit_stats"),
        path("audit/security-report/", SecurityReportView.as_view(), name="audit_security_report"),
        path("audit/event/<int:event_id>/", AuditEventDetailView.as_view(), name="audit_event_detail"),
        path("audit/meta/", AuditEventTypesView.as_view(), name="audit_event_types"),
    ]
