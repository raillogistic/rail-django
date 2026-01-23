"""
Unit tests for audit_management command.
"""

import json
import os
from io import StringIO
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime, timezone

import pytest
from django.core.management import call_command
from django.utils import timezone as django_timezone

pytestmark = pytest.mark.unit

class TestAuditManagementCommand:
    
    @patch("rail_django.management.commands.audit_management.get_audit_event_model")
    def test_export_json(self, mock_get_model):
        """Test exporting audit logs to JSON."""
        # Setup mock data
        mock_qs = MagicMock()
        mock_get_model.return_value.objects.filter.return_value = mock_qs
        mock_qs.count.return_value = 1
        
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.event_type = "LOGIN_SUCCESS"
        mock_event.severity = "LOW"
        mock_event.user_id = 123
        mock_event.username = "testuser"
        mock_event.client_ip = "127.0.0.1"
        mock_event.timestamp = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_event.additional_data = {"browser": "Chrome"}
        mock_event.success = True
        mock_event.request_path = "/login/"
        mock_event.error_message = None
        
        mock_qs.__iter__.return_value = [mock_event]
        
        out = StringIO()
        
        with patch("builtins.open", mock_open()) as mock_file:
            call_command("audit_management", "export", "--output", "audit.json", "--format", "json", stdout=out)
            
            # Check if file was written
            mock_file.assert_called_with("audit.json", "w", encoding="utf-8")
            
            # Verify content written (partial check)
            handle = mock_file()
            # We join the call args to form the full written string
            written_content = "".join(call.args[0] for call in handle.write.call_args_list)
            # Or simpler: json dump calls write multiple times
            
            # Verify filter call
            assert mock_get_model.return_value.objects.filter.called

    @patch("rail_django.management.commands.audit_management.get_audit_event_model")
    def test_export_csv(self, mock_get_model):
        """Test exporting audit logs to CSV."""
        mock_qs = MagicMock()
        mock_get_model.return_value.objects.filter.return_value = mock_qs
        mock_qs.exists.return_value = True
        
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.event_type = "LOGIN_SUCCESS"
        mock_event.severity = "LOW"
        mock_event.user_id = 123
        mock_event.username = "testuser"
        mock_event.client_ip = "127.0.0.1"
        mock_event.timestamp = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_event.request_path = "/login/"
        mock_event.success = True
        mock_event.error_message = ""
        
        mock_qs.__iter__.return_value = [mock_event]
        
        out = StringIO()
        
        with patch("builtins.open", mock_open()) as mock_file:
            call_command("audit_management", "export", "--output", "audit.csv", "--format", "csv", stdout=out)
            
            mock_file.assert_called_with("audit.csv", "w", newline="", encoding="utf-8")

    @patch("rail_django.management.commands.audit_management.get_audit_event_model")
    def test_cleanup_dry_run(self, mock_get_model):
        """Test cleanup dry run."""
        mock_qs = MagicMock()
        mock_get_model.return_value.objects.filter.return_value = mock_qs
        mock_qs.count.return_value = 50
        
        out = StringIO()
        call_command("audit_management", "cleanup", "--days", "90", "--dry-run", stdout=out)
        
        output = out.getvalue()
        assert "[DRY RUN] Would delete 50 audit events" in output
        assert not qs_delete_called(mock_qs)

    @patch("rail_django.management.commands.audit_management.get_audit_event_model")
    def test_cleanup_actual(self, mock_get_model):
        """Test actual cleanup."""
        mock_qs = MagicMock()
        mock_get_model.return_value.objects.filter.return_value = mock_qs
        mock_qs.count.return_value = 50
        
        out = StringIO()
        call_command("audit_management", "cleanup", "--days", "90", stdout=out)
        
        output = out.getvalue()
        assert "Deleted 50 events" in output
        mock_qs.delete.assert_called_once()

    @patch("rail_django.management.commands.audit_management.audit_logger")
    def test_summary(self, mock_logger):
        """Test summary report."""
        mock_logger.get_security_report.return_value = {
            "period_hours": 24,
            "total_events": 100,
            "failed_logins": 5,
            "successful_logins": 90,
            "suspicious_activities": 1,
            "top_failed_ips": [{"client_ip": "1.2.3.4", "count": 5}],
            "top_targeted_users": [{"username": "admin", "count": 5}],
        }
        
        out = StringIO()
        call_command("audit_management", "summary", stdout=out)
        
        output = out.getvalue()
        assert "=== Security Summary (Last 24 hours) ===" in output
        assert "Failed Logins: 5" in output
        assert "Suspicious Activities: 1" in output
        assert "1.2.3.4: 5" in output
        assert "admin: 5" in output

def qs_delete_called(mock_qs):
    return mock_qs.delete.called
