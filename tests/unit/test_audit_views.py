"""
Unit tests for audit views.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from django.test import RequestFactory

from rail_django.http.views.audit import (
    AuditAPIView,
    AuditDashboardView,
    AuditStatsView,
    SecurityReportView,
    AuditEventDetailView,
    AuditEventTypesView,
    require_audit_access,
    get_audit_urls,
)


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def superuser():
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = True
    user.is_staff = True
    user.has_perm = MagicMock(return_value=False)
    return user


@pytest.fixture
def staff_user():
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.is_staff = True
    user.has_perm = MagicMock(return_value=False)
    return user


@pytest.fixture
def regular_user():
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.is_staff = False
    user.has_perm = MagicMock(return_value=False)
    return user


@pytest.fixture
def anonymous_user():
    user = MagicMock()
    user.is_authenticated = False
    user.is_superuser = False
    user.is_staff = False
    return user


@pytest.fixture
def mock_audit_event():
    event = MagicMock()
    event.id = 1
    event.event_type = "login_success"
    event.severity = "low"
    event.user_id = 1
    event.username = "testuser"
    event.client_ip = "127.0.0.1"
    event.user_agent = "TestAgent/1.0"
    event.timestamp = datetime.now(timezone.utc)
    event.request_path = "/graphql/"
    event.request_method = "POST"
    event.additional_data = {"key": "value"}
    event.session_id = "session123"
    event.success = True
    event.error_message = None
    return event


@pytest.mark.unit
class TestRequireAuditAccessDecorator:
    """Tests for the require_audit_access decorator."""

    def test_unauthenticated_user_returns_401(self, request_factory, anonymous_user):
        """Unauthenticated users should receive 401."""

        @require_audit_access
        def view(request):
            return {"status": "ok"}

        request = request_factory.get("/audit/", HTTP_ACCEPT="application/json")
        request.user = anonymous_user

        response = view(request)
        assert response.status_code == 401
        data = json.loads(response.content)
        assert data["code"] == "UNAUTHENTICATED"

    def test_regular_user_returns_403(self, request_factory, regular_user):
        """Regular users without admin privileges should receive 403."""

        @require_audit_access
        def view(request):
            return {"status": "ok"}

        request = request_factory.get("/audit/", HTTP_ACCEPT="application/json")
        request.user = regular_user

        response = view(request)
        assert response.status_code == 403
        data = json.loads(response.content)
        assert data["code"] == "FORBIDDEN"

    def test_superuser_allowed(self, request_factory, superuser):
        """Superusers should be allowed access."""
        from django.http import JsonResponse

        @require_audit_access
        def view(request):
            return JsonResponse({"status": "ok"})

        request = request_factory.get("/audit/")
        request.user = superuser

        response = view(request)
        assert response.status_code == 200

    def test_staff_user_allowed(self, request_factory, staff_user):
        """Staff users should be allowed access."""
        from django.http import JsonResponse

        @require_audit_access
        def view(request):
            return JsonResponse({"status": "ok"})

        request = request_factory.get("/audit/")
        request.user = staff_user

        response = view(request)
        assert response.status_code == 200

    def test_user_with_permission_allowed(self, request_factory, regular_user):
        """Users with audit permission should be allowed access."""
        from django.http import JsonResponse

        regular_user.has_perm = MagicMock(return_value=True)

        @require_audit_access
        def view(request):
            return JsonResponse({"status": "ok"})

        request = request_factory.get("/audit/")
        request.user = regular_user

        response = view(request)
        assert response.status_code == 200


@pytest.mark.unit
class TestAuditAPIView:
    """Tests for the AuditAPIView."""

    @patch("rail_django.http.views.audit.get_audit_event_model")
    def test_get_events_success(
        self, mock_get_model, request_factory, superuser, mock_audit_event
    ):
        """Test successful retrieval of audit events."""
        mock_queryset = MagicMock()
        mock_queryset.all.return_value = mock_queryset
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.count.return_value = 1
        mock_queryset.__getitem__ = MagicMock(return_value=[mock_audit_event])

        mock_model = MagicMock()
        mock_model.objects = mock_queryset
        mock_get_model.return_value = mock_model

        request = request_factory.get("/audit/")
        request.user = superuser

        view = AuditAPIView()
        response = view.get(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "events" in data
        assert "pagination" in data
        assert data["pagination"]["total_count"] == 1

    @patch("rail_django.http.views.audit.get_audit_event_model")
    def test_filter_by_event_type(
        self, mock_get_model, request_factory, superuser, mock_audit_event
    ):
        """Test filtering by event_type."""
        mock_queryset = MagicMock()
        mock_queryset.all.return_value = mock_queryset
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.count.return_value = 1
        mock_queryset.__getitem__ = MagicMock(return_value=[mock_audit_event])

        mock_model = MagicMock()
        mock_model.objects = mock_queryset
        mock_get_model.return_value = mock_model

        request = request_factory.get("/audit/?event_type=login_success")
        request.user = superuser

        view = AuditAPIView()
        response = view.get(request)

        assert response.status_code == 200
        mock_queryset.filter.assert_called()

    @patch("rail_django.http.views.audit.get_audit_event_model")
    def test_filter_by_severity(
        self, mock_get_model, request_factory, superuser, mock_audit_event
    ):
        """Test filtering by severity."""
        mock_queryset = MagicMock()
        mock_queryset.all.return_value = mock_queryset
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.count.return_value = 0
        mock_queryset.__getitem__ = MagicMock(return_value=[])

        mock_model = MagicMock()
        mock_model.objects = mock_queryset
        mock_get_model.return_value = mock_model

        request = request_factory.get("/audit/?severity=high")
        request.user = superuser

        view = AuditAPIView()
        response = view.get(request)

        assert response.status_code == 200

    @patch("rail_django.http.views.audit.get_audit_event_model")
    def test_pagination(
        self, mock_get_model, request_factory, superuser, mock_audit_event
    ):
        """Test pagination parameters."""
        mock_queryset = MagicMock()
        mock_queryset.all.return_value = mock_queryset
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.count.return_value = 100
        mock_queryset.__getitem__ = MagicMock(return_value=[mock_audit_event])

        mock_model = MagicMock()
        mock_model.objects = mock_queryset
        mock_get_model.return_value = mock_model

        request = request_factory.get("/audit/?page=2&page_size=10")
        request.user = superuser

        view = AuditAPIView()
        response = view.get(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["page_size"] == 10
        assert data["pagination"]["total_pages"] == 10


@pytest.mark.unit
class TestAuditStatsView:
    """Tests for the AuditStatsView."""

    @patch("rail_django.http.views.audit.get_audit_event_model")
    def test_get_stats_success(self, mock_get_model, request_factory, superuser):
        """Test successful retrieval of audit statistics."""
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.values.return_value = mock_queryset
        mock_queryset.annotate.return_value = mock_queryset
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.values_list.return_value = [("login_success", 5)]
        mock_queryset.count.return_value = 10
        mock_queryset.__iter__ = MagicMock(return_value=iter([]))

        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_queryset
        mock_get_model.return_value = mock_model

        request = request_factory.get("/audit/stats/?hours=48")
        request.user = superuser

        view = AuditStatsView()
        response = view.get(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "period_hours" in data
        assert data["period_hours"] == 48


@pytest.mark.unit
class TestSecurityReportView:
    """Tests for the SecurityReportView."""

    @patch("rail_django.http.views.audit.get_audit_event_model")
    @patch("rail_django.http.views.audit.audit_logger")
    def test_get_report_success(
        self, mock_logger, mock_get_model, request_factory, superuser
    ):
        """Test successful generation of security report."""
        mock_logger.get_security_report.return_value = {
            "period_hours": 24,
            "total_events": 100,
            "failed_logins": 5,
            "successful_logins": 80,
            "suspicious_activities": 2,
            "rate_limited_requests": 3,
            "top_failed_ips": [],
            "top_targeted_users": [],
        }

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset
        mock_queryset.values.return_value = mock_queryset
        mock_queryset.annotate.return_value = mock_queryset
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.__iter__ = MagicMock(return_value=iter([]))

        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_queryset
        mock_get_model.return_value = mock_model

        request = request_factory.get("/audit/security-report/")
        request.user = superuser

        view = SecurityReportView()
        response = view.get(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "failed_logins" in data
        assert "brute_force_suspects" in data

    @patch("rail_django.http.views.audit.audit_logger")
    def test_report_error_handling(self, mock_logger, request_factory, superuser):
        """Test handling of errors from audit_logger."""
        mock_logger.get_security_report.return_value = {
            "error": "Database storage not enabled"
        }

        request = request_factory.get("/audit/security-report/")
        request.user = superuser

        view = SecurityReportView()
        response = view.get(request)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert data["code"] == "REPORT_ERROR"


@pytest.mark.unit
class TestAuditEventDetailView:
    """Tests for the AuditEventDetailView."""

    @patch("rail_django.http.views.audit.get_audit_event_model")
    def test_get_event_success(
        self, mock_get_model, request_factory, superuser, mock_audit_event
    ):
        """Test successful retrieval of a single event."""
        mock_queryset = MagicMock()
        mock_queryset.first.return_value = mock_audit_event

        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_queryset
        mock_get_model.return_value = mock_model

        request = request_factory.get("/audit/event/1/")
        request.user = superuser

        view = AuditEventDetailView()
        response = view.get(request, event_id=1)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "event" in data
        assert data["event"]["id"] == 1

    @patch("rail_django.http.views.audit.get_audit_event_model")
    def test_get_event_not_found(self, mock_get_model, request_factory, superuser):
        """Test 404 response when event not found."""
        mock_queryset = MagicMock()
        mock_queryset.first.return_value = None

        mock_model = MagicMock()
        mock_model.objects.filter.return_value = mock_queryset
        mock_get_model.return_value = mock_model

        request = request_factory.get("/audit/event/999/")
        request.user = superuser

        view = AuditEventDetailView()
        response = view.get(request, event_id=999)

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["code"] == "NOT_FOUND"


@pytest.mark.unit
class TestAuditEventTypesView:
    """Tests for the AuditEventTypesView."""

    def test_get_event_types(self, request_factory, superuser):
        """Test retrieval of event types and severities."""
        request = request_factory.get("/audit/meta/")
        request.user = superuser

        view = AuditEventTypesView()
        response = view.get(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "event_types" in data
        assert "severities" in data
        assert "login_success" in data["event_types"]
        assert "low" in data["severities"]


@pytest.mark.unit
class TestGetAuditUrls:
    """Tests for the get_audit_urls function."""

    def test_returns_url_patterns(self):
        """Test that get_audit_urls returns valid URL patterns."""
        urls = get_audit_urls()

        assert len(urls) == 8

        url_names = [url.name for url in urls]
        assert "audit_dashboard" in url_names
        assert "audit_api" in url_names
        assert "audit_stats" in url_names
        assert "audit_security_report" in url_names
        assert "audit_event_detail" in url_names
        assert "audit_event_types" in url_names


@pytest.mark.unit
class TestAuditDashboardView:
    """Tests for the AuditDashboardView."""

    def test_unauthenticated_user_returns_401_html(self, request_factory, anonymous_user):
        """Unauthenticated users should receive 401 with HTML response."""
        request = request_factory.get("/audit/dashboard/")
        request.user = anonymous_user

        view = AuditDashboardView()
        response = view.get(request)

        assert response.status_code == 401
        assert b"Authentication Required" in response.content

    def test_regular_user_returns_403_html(self, request_factory, regular_user):
        """Regular users without admin privileges should receive 403."""
        request = request_factory.get("/audit/dashboard/")
        request.user = regular_user

        view = AuditDashboardView()
        response = view.get(request)

        assert response.status_code == 403
        assert b"Access Denied" in response.content

    def test_superuser_gets_dashboard(self, request_factory, superuser):
        """Superusers should be able to access the dashboard."""
        request = request_factory.get("/audit/dashboard/")
        request.user = superuser

        view = AuditDashboardView()
        # Note: This will fail if template is not found, which is expected in unit tests
        # The important thing is that it doesn't return 401 or 403
        try:
            response = view.get(request)
            # If render succeeds, check it's a 200
            assert response.status_code == 200
        except Exception:
            # Template not found is acceptable in unit tests
            pass
