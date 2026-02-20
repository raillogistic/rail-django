from unittest.mock import Mock, patch

import pytest

from rail_django.security.events.sinks.database import (
    DatabaseSink,
    _normalize_client_ip,
)
from rail_django.security.events.types import EventType, SecurityEvent


@pytest.mark.unit
def test_normalize_client_ip_rejects_placeholder_values():
    assert _normalize_client_ip("unknown") is None
    assert _normalize_client_ip("  ") is None
    assert _normalize_client_ip(None) is None
    assert _normalize_client_ip("not-an-ip") is None


@pytest.mark.unit
def test_normalize_client_ip_accepts_common_forms():
    assert _normalize_client_ip("1.2.3.4") == "1.2.3.4"
    assert _normalize_client_ip("1.2.3.4:54432") == "1.2.3.4"
    assert _normalize_client_ip("1.2.3.4, 5.6.7.8") == "1.2.3.4"
    assert _normalize_client_ip("[2001:db8::1]:443") == "2001:db8::1"


@pytest.mark.unit
def test_database_sink_writes_null_ip_for_invalid_client_ip():
    sink = DatabaseSink()
    event = SecurityEvent(
        event_type=EventType.DATA_UPDATE,
        correlation_id="corr-1",
        client_ip="unknown",
    )

    fake_model = Mock()
    with patch(
        "rail_django.extensions.audit.models.get_audit_event_model",
        return_value=fake_model,
    ):
        sink.write(event)

    kwargs = fake_model.objects.create.call_args.kwargs
    assert kwargs["client_ip"] is None

