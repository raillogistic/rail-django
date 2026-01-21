"""
Unit tests for Phase 5 security hardening.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import graphene
import pytest
from django.test import override_settings

from rail_django.core.middleware import AccessGuardMiddleware
from rail_django.extensions.audit import AuditEvent, AuditEventType, AuditLogger, AuditSeverity
from rail_django.extensions.auth import set_auth_cookies
from rail_django.security.validation import InputValidator
from rail_django.testing import RailGraphQLTestClient, override_rail_settings

pytestmark = pytest.mark.unit

INTROSPECTION_QUERY = """
query {
  __schema {
    types {
      name
    }
  }
}
"""


class _UserStub:
    def __init__(self, user_id: int, *, is_superuser: bool = False):
        self.id = user_id
        self.is_authenticated = True
        self.is_superuser = is_superuser


def _first_error_message(result):
    errors = result.get("errors") or []
    if not errors:
        return ""
    error = errors[0]
    if isinstance(error, dict):
        return error.get("message", "")
    return str(error)


def _build_schema():
    class Query(graphene.ObjectType):
        ping = graphene.String()

        def resolve_ping(root, info):
            return "pong"

    return graphene.Schema(query=Query)


def test_access_guard_blocks_unauthenticated_when_required():
    schema = _build_schema()
    with override_rail_settings(
        global_settings={"schema_settings": {"authentication_required": True}}
    ):
        client = RailGraphQLTestClient(schema, schema_name="guard")
        result = client.execute(
            "{ ping }",
            middleware=[AccessGuardMiddleware("guard")],
        )

    assert result.get("errors")
    assert "Authentication required" in _first_error_message(result)


def test_access_guard_blocks_introspection_when_disabled():
    schema = _build_schema()
    with override_rail_settings(
        global_settings={
            "schema_settings": {
                "authentication_required": False,
                "enable_introspection": False,
            }
        }
    ):
        client = RailGraphQLTestClient(schema, schema_name="guard")
        result = client.execute(
            INTROSPECTION_QUERY,
            middleware=[AccessGuardMiddleware("guard")],
        )

    assert result.get("errors")
    assert "Introspection not permitted" in _first_error_message(result)


def test_access_guard_allows_introspection_for_roles():
    schema = _build_schema()
    user = _UserStub(1)
    with override_rail_settings(
        global_settings={
            "schema_settings": {
                "authentication_required": False,
                "enable_introspection": False,
            },
            "security_settings": {"introspection_roles": ["admin"]},
        },
    ):
        client = RailGraphQLTestClient(schema, schema_name="guard", user=user)
        with patch(
            "rail_django.core.security.role_manager.get_user_roles",
            return_value=["admin"],
        ):
            result = client.execute(
                INTROSPECTION_QUERY,
                user=user,
                middleware=[AccessGuardMiddleware("guard")],
            )

    assert result.get("errors") is None


def test_input_validation_respects_failure_severity():
    payload = {"name": "abcd"}

    with override_rail_settings(
        schema_settings={
            "validation": {
                "security_settings": {
                    "input_max_string_length": 3,
                    "input_truncate_long_strings": False,
                    "input_failure_severity": "critical",
                }
            }
        }
    ):
        validator = InputValidator(schema_name="validation")
        report = validator.validate_payload(payload)
        assert not report.has_failures()

    with override_rail_settings(
        schema_settings={
            "validation": {
                "security_settings": {
                    "input_max_string_length": 3,
                    "input_truncate_long_strings": False,
                    "input_failure_severity": "high",
                }
            }
        }
    ):
        validator = InputValidator(schema_name="validation")
        report = validator.validate_payload(payload)
        assert report.has_failures()


def test_audit_logger_redacts_sensitive_fields():
    with override_settings(
        GRAPHQL_ENABLE_AUDIT_LOGGING=True,
        AUDIT_STORE_IN_DATABASE=False,
        AUDIT_STORE_IN_FILE=False,
        AUDIT_REDACTION_FIELDS=["password", "token"],
        AUDIT_REDACTION_MASK="***",
        AUDIT_REDACT_ERROR_MESSAGES=True,
    ):
        logger = AuditLogger()
        event = AuditEvent(
            event_type=AuditEventType.LOGIN_FAILURE,
            severity=AuditSeverity.MEDIUM,
            client_ip="127.0.0.1",
            user_agent="test",
            timestamp=datetime.now(timezone.utc),
            request_path="/graphql/",
            request_method="POST",
            additional_data={
                "password": "secret",
                "nested": {"token": "abc"},
                "safe": "ok",
            },
            error_message="password invalid",
        )

        redacted = logger._redact_event(event)

    assert redacted.additional_data["password"] == "***"
    assert redacted.additional_data["nested"]["token"] == "***"
    assert redacted.additional_data["safe"] == "ok"
    assert redacted.error_message == "***"


def test_set_auth_cookies_respects_policy_overrides():
    request = SimpleNamespace()
    with override_settings(
        DEBUG=False,
        JWT_AUTH_COOKIE="jwt",
        JWT_REFRESH_COOKIE="refresh",
        JWT_AUTH_COOKIE_SECURE=True,
        JWT_AUTH_COOKIE_SAMESITE="Strict",
        JWT_AUTH_COOKIE_DOMAIN="example.com",
        JWT_AUTH_COOKIE_PATH="/auth",
        JWT_REFRESH_COOKIE_SECURE=False,
        JWT_REFRESH_COOKIE_SAMESITE="Lax",
        JWT_REFRESH_COOKIE_DOMAIN="example.com",
        JWT_REFRESH_COOKIE_PATH="/refresh",
        JWT_ACCESS_TOKEN_LIFETIME=3600,
        JWT_REFRESH_TOKEN_LIFETIME=7200,
    ):
        set_auth_cookies(request, access_token="access", refresh_token="refresh")

    cookies = request._set_auth_cookies
    auth_cookie = next(item for item in cookies if item["key"] == "jwt")
    refresh_cookie = next(item for item in cookies if item["key"] == "refresh")

    assert auth_cookie["secure"] is True
    assert auth_cookie["samesite"] == "Strict"
    assert auth_cookie["domain"] == "example.com"
    assert auth_cookie["path"] == "/auth"

    assert refresh_cookie["secure"] is False
    assert refresh_cookie["samesite"] == "Lax"
    assert refresh_cookie["domain"] == "example.com"
    assert refresh_cookie["path"] == "/refresh"
