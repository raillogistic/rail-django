# Input validation

Rail Django includes a unified input validation pipeline in
`rail_django.security.validation`. It sanitizes incoming payloads, applies
pattern checks, and produces structured validation reports.

## Use the validation decorator

Use `@validate_input` on resolvers or handlers where you need explicit input
validation.

```python
from rail_django.security.validation import validate_input

@validate_input()
def resolve_create_comment(root, info, input):
    return Comment.objects.create(**input)
```

## Use the global validator

For manual checks, use `input_validator`.

```python
from rail_django.security.validation import input_validator

report = input_validator.validate_payload({"email": "person@example.com"})
if report.has_issues:
    raise ValueError("Input payload failed validation")
```

## Security settings

These keys are read from `RAIL_DJANGO_GRAPHQL["security_settings"]`.

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_input_validation": True,
        "enable_sql_injection_protection": True,
        "enable_xss_protection": True,
        "input_allow_html": False,
        "input_allowed_html_tags": ["p", "br", "strong", "em"],
        "input_allowed_html_attributes": {"a": ["href", "title"]},
        "input_max_string_length": None,
        "input_truncate_long_strings": False,
        "input_failure_severity": "high",
        "input_pattern_scan_limit": 10000,
    }
}
```

## Validate and sanitize payloads

For explicit sanitize-and-raise behavior, use the sanitizer API.

```python
from rail_django.security.validation import graphql_sanitizer

clean_payload = graphql_sanitizer.sanitize_and_validate(payload)
```

## Next steps

Continue with [permissions](./permissions.md) and
[core mutations](../core/mutations.md).
