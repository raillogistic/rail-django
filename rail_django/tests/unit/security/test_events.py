import pytest
from rail_django.security.events.types import (
    SecurityEvent, EventType, Severity, Outcome, Resource, EventCategory
)
from rail_django.security.events.builder import event, EventBuilder


@pytest.mark.unit
class TestSecurityEvent:
    def test_category_derived_from_type(self):
        evt = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_SUCCESS,
            correlation_id="test-123"
        )
        assert evt.category == EventCategory.AUTHENTICATION

    def test_to_dict_serialization(self):
        evt = SecurityEvent(
            event_type=EventType.DATA_READ,
            correlation_id="test-123",
            user_id=1,
            resource=Resource(type="model", name="User", id="42")
        )
        data = evt.to_dict()

        assert data["event_type"] == "data.read"
        assert data["category"] == "data"
        assert data["resource"]["name"] == "User"
        assert "timestamp" in data


@pytest.mark.unit
class TestEventBuilder:
    def test_fluent_building(self):
        evt = (
            event(EventType.AUTH_LOGIN_FAILURE)
            .action("Failed login attempt")
            .outcome(Outcome.FAILURE)
            .context(username_attempted="admin")
            .error("Invalid credentials")
            .build()
        )

        assert evt.event_type == EventType.AUTH_LOGIN_FAILURE
        assert evt.outcome == Outcome.FAILURE
        assert evt.context["username_attempted"] == "admin"
        assert evt.error_message == "Invalid credentials"
        assert evt.severity == Severity.WARNING  # default for login failure

    def test_resource_builder(self):
        evt = (
            event(EventType.DATA_DELETE)
            .resource("model", "User", "123")
            .build()
        )

        assert evt.resource.type == "model"
        assert evt.resource.name == "User"
        assert evt.resource.id == "123"
