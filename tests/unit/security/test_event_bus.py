import pytest
from django.test import override_settings
from unittest.mock import Mock, patch
from rail_django.security.events.types import SecurityEvent, EventType, Outcome
from rail_django.security.events.bus import EventBus, EventRedactor
from rail_django.security.events.sinks.base import EventSink


class MockSink(EventSink):
    def __init__(self):
        self.events = []

    def write(self, event):
        self.events.append(event)


@pytest.mark.unit
class TestEventBus:
    def test_sync_dispatch(self):
        bus = EventBus(async_processing=False)
        sink = MockSink()
        bus.add_sink(sink)

        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_SUCCESS,
            correlation_id="test-123"
        )
        bus.emit(event)

        assert len(sink.events) == 1
        assert sink.events[0].correlation_id == "test-123"

    def test_multiple_sinks(self):
        bus = EventBus(async_processing=False)
        sink1 = MockSink()
        sink2 = MockSink()
        bus.add_sink(sink1).add_sink(sink2)

        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_SUCCESS,
            correlation_id="test-123"
        )
        bus.emit(event)

        assert len(sink1.events) == 1
        assert len(sink2.events) == 1

    def test_sink_error_isolated(self):
        bus = EventBus(async_processing=False)

        failing_sink = Mock(spec=EventSink)
        failing_sink.write.side_effect = Exception("Sink error")

        working_sink = MockSink()

        bus.add_sink(failing_sink).add_sink(working_sink)

        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_SUCCESS,
            correlation_id="test-123"
        )
        bus.emit(event)  # Should not raise

        assert len(working_sink.events) == 1

    @override_settings(
        SECURITY_EVENT_ASYNC=False,
        AUDIT_STORE_IN_DATABASE=False,
        AUDIT_STORE_IN_FILE=True,
        AUDIT_FILE_LOGGER_NAME="audit.custom",
        AUDIT_WEBHOOK_URL=None,
        SECURITY_METRICS_ENABLED=False,
    )
    def test_create_event_bus_uses_configured_file_logger_name(self):
        from rail_django.security.events import bus as bus_module

        with (
            patch("rail_django.security.events.sinks.file.FileSink") as file_sink_cls,
            patch.object(bus_module.EventBus, "start", autospec=True),
        ):
            bus = bus_module._create_event_bus()

        file_sink_cls.assert_called_once_with(logger_name="audit.custom")
        assert len(bus._sinks) == 1


@pytest.mark.unit
class TestEventRedactor:
    def test_redacts_password_fields(self):
        redactor = EventRedactor()
        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_FAILURE,
            correlation_id="test-123",
            context={"username": "admin", "password": "secret123"}
        )

        redacted = redactor.redact(event)

        assert redacted.context["username"] == "admin"
        assert redacted.context["password"] == "***REDACTED***"

    def test_redacts_nested_fields(self):
        redactor = EventRedactor()
        event = SecurityEvent(
            event_type=EventType.DATA_CREATE,
            correlation_id="test-123",
            context={
                "input": {
                    "user": {"name": "John", "token": "abc123"}
                }
            }
        )

        redacted = redactor.redact(event)

        assert redacted.context["input"]["user"]["name"] == "John"
        assert redacted.context["input"]["user"]["token"] == "***REDACTED***"

    def test_original_event_unchanged(self):
        redactor = EventRedactor()
        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_FAILURE,
            correlation_id="test-123",
            context={"password": "secret123"}
        )

        redactor.redact(event)

        assert event.context["password"] == "secret123"  # Original unchanged
