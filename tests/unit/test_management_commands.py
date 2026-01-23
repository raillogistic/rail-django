"""
Unit tests for Rail Django management commands.
"""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.unit

class TestManagementCommands:
    @patch("rail_django.management.commands.startapp.StartAppCommand.handle")
    def test_startapp_custom_template(self, mock_super_handle):
        """Test startapp uses custom template by default."""
        call_command("startapp", "new_app")
        
        args, kwargs = mock_super_handle.call_args
        assert "template" in kwargs
        assert "app_template" in kwargs["template"]

    @patch("rail_django.management.commands.startapp.StartAppCommand.handle")
    def test_startapp_minimal_flag(self, mock_super_handle):
        """Test startapp --minimal uses minimal template."""
        call_command("startapp", "new_app", minimal=True)
        
        args, kwargs = mock_super_handle.call_args
        assert "template" in kwargs
        assert "app_template_minimal" in kwargs["template"]

    @patch("rail_django.management.commands.security_check.Command._perform_security_checks")
    def test_security_check_output_text(self, mock_checks):
        """Test security_check command with text output."""
        mock_checks.return_value = {
            "middleware_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "audit_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "mfa_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "rate_limiting_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "django_security_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "database_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "cache_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "has_critical_issues": False,
            "warnings": [],
            "recommendations": [],
        }
        
        out = StringIO()
        call_command("security_check", stdout=out)
        
        output = out.getvalue()
        assert "CONFIGURATION SÉCURISÉE" in output
        assert "Configuration des Middlewares" in output

    @patch("rail_django.management.commands.security_check.Command._perform_security_checks")
    def test_security_check_critical_fails(self, mock_checks):
        """Test security_check raises CommandError if critical issues found."""
        mock_checks.return_value = {
            "middleware_check": {"status": "critical", "warnings": [], "recommendations": [], "critical_issues": ["Critical problem"]},
            "has_critical_issues": True,
            "warnings": [],
            "recommendations": [],
        }
        
        # We need to provide other keys as well because the command iterates over them
        for key in ["audit_check", "mfa_check", "rate_limiting_check", "django_security_check", "database_check", "cache_check"]:
             mock_checks.return_value[key] = {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []}

        with pytest.raises(CommandError, match="Des problèmes critiques de sécurité ont été détectés"):
            call_command("security_check")

    @patch("rail_django.management.commands.security_check.Command._perform_security_checks")
    def test_security_check_json_output(self, mock_checks):
        """Test security_check command with JSON output."""
        results = {
            "middleware_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "audit_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "mfa_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "rate_limiting_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "django_security_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "database_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "cache_check": {"status": "ok", "warnings": [], "recommendations": [], "critical_issues": []},
            "has_critical_issues": False,
            "warnings": [],
            "recommendations": [],
        }
        mock_checks.return_value = results
        
        out = StringIO()
        call_command("security_check", format="json", stdout=out)
        
        output_json = json.loads(out.getvalue())
        assert output_json["has_critical_issues"] is False
        assert "middleware_check" in output_json
