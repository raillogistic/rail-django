"""A legitimate signed refresh credential must not be treated as SQL text."""

from datetime import datetime, timedelta, timezone
import jwt
import pytest
from django.test import override_settings
from rail_django.security.validation.sanitizer import InputSanitizer
from rail_django.security.validation.types import InputValidationSettings

TEST_KEY = "refresh-validator-test-key-only-0000000000"


def signed_token(*, expired=False, token_type="refresh"):
    """Produce deterministic synthetic signatures containing the SQL comment marker."""
    for nonce in range(2000):
        token = jwt.encode({"type": token_type, "exp": datetime.now(timezone.utc)+timedelta(hours=-1 if expired else 1), "nonce": nonce}, TEST_KEY, algorithm="HS256")
        if "--" in token.rsplit(".", 1)[-1]:
            return token
    raise AssertionError("No synthetic comment-marker signature found")


@pytest.mark.parametrize("field", ["refresh_token", "refreshToken", "input.refreshToken"])
@override_settings(JWT_SECRET_KEY=TEST_KEY)
def test_valid_refresh_signature_is_preserved(field):
    """Verify the full signature/type/expiry before exempting only the credential."""
    token = signed_token()
    result = InputSanitizer(InputValidationSettings()).sanitize_string(token, field=field)
    assert result.is_valid
    assert result.sanitized_value == token


@override_settings(JWT_SECRET_KEY=TEST_KEY)
def test_invalid_expired_wrong_type_and_noncredential_inputs_still_fail():
    """The exemption cannot admit forged credentials or disable SQL guards elsewhere."""
    sanitizer = InputSanitizer(InputValidationSettings())
    token = signed_token()
    for value, field in [(token+"A", "refresh_token"), (signed_token(expired=True), "refresh_token"),
                         (signed_token(token_type="access"), "refresh_token"), (token, "notes"),
                         ("' OR 1=1 --", "refresh_token")]:
        result = sanitizer.sanitize_string(value, field=field)
        assert not result.is_valid
        assert any(issue.code == "SQL_INJECTION_PATTERN" for issue in result.issues)
