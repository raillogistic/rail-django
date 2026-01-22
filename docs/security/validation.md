# Input Validation

Rail Django includes a robust validation system to sanitize inputs and prevent common attacks like XSS and SQL Injection.

## Automatic Sanitization

By default, the framework sanitizes string inputs to strip potentially dangerous characters. This is controlled by `security_settings.enable_input_validation`.

## The `@validate_input` Decorator

You can explicitly validate inputs on any resolver using the `@validate_input` decorator.

```python
from rail_django.security.validation import validate_input

@validate_input()
def resolve_create_comment(root, info, input):
    # 'input' is now sanitized and validated
    return Comment.objects.create(**input)
```

## Global Input Validator

You can use the global `input_validator` for manual checks.

```python
from rail_django.security.validation import input_validator

def my_function(data):
    report = input_validator.validate_payload(data)
    
    if report.has_issues:
        for issue in report.issues:
            print(f"Validation error in {issue.path}: {issue.message}")
        raise ValueError("Invalid input")
```

## Configuration

You can customize the HTML sanitizer and severity thresholds in `settings.py`.

```python
# settings.py
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "input_allowed_html_tags": ["b", "i", "u", "a"],
        "input_allowed_html_attributes": {"a": ["href"]},
        "input_failure_severity": "high", # Only block 'high' severity issues
        "enable_sql_injection_protection": True,
        "enable_xss_protection": True,
    }
}
```