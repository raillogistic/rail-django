import pytest
from django.test import RequestFactory
from rail_django.security.context import SecurityContext, Actor, get_client_ip
from rail_django.security.middleware.context import SecurityContextMiddleware, get_security_context


@pytest.mark.unit
class TestSecurityContext:
    def test_from_request_anonymous(self):
        factory = RequestFactory()
        request = factory.get("/graphql/")
        ctx = SecurityContext.from_request(request)

        assert ctx.correlation_id is not None
        assert len(ctx.correlation_id) == 36  # UUID format
        assert ctx.actor.user_id is None
        assert ctx.request_path == "/graphql/"
        assert ctx.risk_score == 0.0

    def test_correlation_id_from_header(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_CORRELATION_ID="test-123")
        ctx = SecurityContext.from_request(request)
        assert ctx.correlation_id == "test-123"

    def test_add_risk_accumulates(self):
        factory = RequestFactory()
        request = factory.get("/")
        ctx = SecurityContext.from_request(request)

        ctx.add_risk(20.0, "suspicious_pattern")
        ctx.add_risk(30.0, "sensitive_field_access")

        assert ctx.risk_score == 50.0
        assert len(ctx.metadata["risk_reasons"]) == 2

    def test_risk_score_capped_at_100(self):
        factory = RequestFactory()
        request = factory.get("/")
        ctx = SecurityContext.from_request(request)

        ctx.add_risk(60.0, "reason1")
        ctx.add_risk(60.0, "reason2")

        assert ctx.risk_score == 100.0


@pytest.mark.unit
class TestGetClientIp:
    def test_x_forwarded_for(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
        assert get_client_ip(request) == "1.2.3.4"

    def test_x_real_ip(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_REAL_IP="9.8.7.6")
        assert get_client_ip(request) == "9.8.7.6"

    def test_remote_addr_fallback(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        assert get_client_ip(request) == "127.0.0.1"
