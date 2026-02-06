# Backend Rollback Playbook

1. Revert table v3 schema registration in deployment config.
2. Clear table cache prefixes (`table:bootstrap:*`, `table:rows:*`).
3. Run `python manage.py rollback_check`.
4. Validate bootstrap/rows/action paths in staging before prod rollback.
