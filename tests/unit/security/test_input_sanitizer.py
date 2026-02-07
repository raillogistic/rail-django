import pytest

from rail_django.security.validation.sanitizer import InputSanitizer
from rail_django.security.validation.types import InputValidationSettings


pytestmark = pytest.mark.unit


def test_mode_enum_value_is_not_flagged_as_sql_injection():
    sanitizer = InputSanitizer(InputValidationSettings())

    result = sanitizer.sanitize_string("UPDATE", field="mode")

    assert result.is_valid is True
    assert not any(issue.code == "SQL_INJECTION_PATTERN" for issue in result.issues)


def test_sql_injection_pattern_is_still_detected_for_normal_field():
    sanitizer = InputSanitizer(InputValidationSettings())

    result = sanitizer.sanitize_string("SELECT * FROM users", field="name")

    assert result.is_valid is False
    assert any(issue.code == "SQL_INJECTION_PATTERN" for issue in result.issues)
