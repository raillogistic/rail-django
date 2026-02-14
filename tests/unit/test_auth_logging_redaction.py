from rail_django.extensions.auth.mutations import _redact_auth_log_value


def test_redact_auth_log_value_masks_password_and_token_pairs():
    source = "login failed token=super-secret password=my-password authorization=Bearer123"
    redacted = _redact_auth_log_value(source)

    assert "super-secret" not in redacted
    assert "my-password" not in redacted
    assert "Bearer123" not in redacted
    assert redacted.count("[REDACTED]") >= 3


def test_redact_auth_log_value_handles_dictionary_payloads():
    payload = {
        "username": "user1",
        "password": "plain-password",
        "token": "plain-token",
    }
    redacted = _redact_auth_log_value(payload)

    assert "plain-password" not in redacted
    assert "plain-token" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_auth_log_value_keeps_non_sensitive_content():
    text = "Invalid credentials for username: test_user"
    redacted = _redact_auth_log_value(text)
    assert redacted == text
