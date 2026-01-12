"""
Integration tests for Phase 5 security hardening.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from rail_django.extensions.audit import AuditLogger, AuditEventType, AuditSeverity, get_audit_event_model
from rail_django.extensions.auth import JWTManager

pytestmark = pytest.mark.integration


class TestJwtRotation(TestCase):
    def test_refresh_rotation_detects_reuse(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="jwt_user",
            email="jwt@example.com",
            password="testpass123",
        )

        with override_settings(
            JWT_ROTATE_REFRESH_TOKENS=True,
            JWT_REFRESH_REUSE_DETECTION=True,
            JWT_REFRESH_TOKEN_CACHE="jwt_refresh",
            JWT_ACCESS_TOKEN_LIFETIME=3600,
            JWT_REFRESH_TOKEN_LIFETIME=7200,
            CACHES={
                "jwt_refresh": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
                }
            },
        ):
            token_data = JWTManager.generate_token(user)
            refresh_token = token_data["refresh_token"]

            refreshed = JWTManager.refresh_token(refresh_token)
            assert refreshed is not None
            assert refreshed["refresh_token"] is not None
            assert refreshed["refresh_token"] != refresh_token

            reused = JWTManager.refresh_token(refresh_token)
            assert reused is None


class TestAuditRetention(TestCase):
    def test_audit_retention_deletes_old_events(self):
        with override_settings(
            GRAPHQL_ENABLE_AUDIT_LOGGING=True,
            AUDIT_STORE_IN_DATABASE=True,
            AUDIT_STORE_IN_FILE=False,
            AUDIT_RETENTION_DAYS=1,
            AUDIT_RETENTION_RUN_INTERVAL=0,
        ):
            logger = AuditLogger()
            model = get_audit_event_model()

            old_event = model.objects.create(
                event_type=AuditEventType.LOGIN_FAILURE.value,
                severity=AuditSeverity.MEDIUM.value,
                timestamp=timezone.now() - timedelta(days=2),
                client_ip="127.0.0.1",
            )
            recent_event = model.objects.create(
                event_type=AuditEventType.LOGIN_SUCCESS.value,
                severity=AuditSeverity.LOW.value,
                timestamp=timezone.now(),
                client_ip="127.0.0.1",
            )

            logger._apply_retention_policy()

            assert not model.objects.filter(pk=old_event.pk).exists()
            assert model.objects.filter(pk=recent_event.pk).exists()
