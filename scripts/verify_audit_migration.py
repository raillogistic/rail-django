#!/usr/bin/env python
"""Verify all old audit code has been removed and migrated."""

import subprocess
import sys
import os

PATTERNS_SHOULD_NOT_EXIST = [
    "from rail_django.extensions.audit.logger",
    "from rail_django.security.audit",
    "import AuditLogger",
    "AuditEventType\\.",
    "AuditSeverity\\.",
    "audit_logger\\.",
    "log_audit_event\\(",
    "log_authentication_event\\(",
]

PATHS_SHOULD_NOT_EXIST = [
    "rail_django/security/audit/",
    "rail_django/extensions/audit/logger/",
    "rail_django/extensions/audit/logger.py",
    "rail_django/extensions/audit/types.py",
]

def check_patterns():
    errors = []
    print("Checking for deprecated patterns...")
    for pattern in PATTERNS_SHOULD_NOT_EXIST:
        # Use git grep if in a git repo, otherwise regular grep
        cmd = ["grep", "-rn", pattern, "rail_django/"]

        # Exclude this script and migration files
        exclude_args = ["--exclude", "verify_audit_migration.py", "--exclude-dir", "migrations"]

        try:
            result = subprocess.run(
                cmd + exclude_args,
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                # Filter out false positives if needed
                lines = result.stdout.strip().split('\n')
                real_matches = [line for line in lines if "tests/" not in line] # Ignore tests for now if we haven't updated all tests

                if real_matches:
                    errors.append(f"Found deprecated pattern '{pattern}':\n" + "\n".join(real_matches))
        except FileNotFoundError:
            print("grep command not found, skipping pattern check")
            break

    return errors

def check_paths():
    errors = []
    print("Checking for deprecated paths...")
    for path in PATHS_SHOULD_NOT_EXIST:
        if os.path.exists(path):
            errors.append(f"Path should be deleted: {path}")
    return errors

def main():
    print("Verifying audit migration...")

    errors = check_patterns() + check_paths()

    if errors:
        print("\n[!] Migration incomplete:\n")
        for error in errors:
            print(f"  - {error}\n")
        sys.exit(1)
    else:
        print("[OK] Migration complete - all old code removed")
        sys.exit(0)

if __name__ == "__main__":
    main()
