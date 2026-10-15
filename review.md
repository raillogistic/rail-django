# Repository Review and Remediation

Date: 2026-07-27  
Base revision: `611e78e0` (`v0.1.42`)  
Status: **11 of 11 findings resolved**

## Executive summary

The repository-wide review found 11 security, correctness, reliability, and
performance issues: 5 high, 5 medium, and 1 low severity. All 11 have been
addressed in the working tree.

The main query improvements move task filtering and limiting into SQL, enforce
the configured maximum page size on standard list queries, add task lookup
indexes, and stop unbounded Python property-filter scans. Other unbounded work
was removed or capped, including log tailing and fabricated health history.

The final full test run is green:

```text
1456 passed, 10 skipped, 2 warnings, 3 subtests passed in 549.57s
```

## Resolved findings

| # | Severity | Finding | Resolution |
| ---: | --- | --- | --- |
| 1 | High | Insecure scaffolded password reset | Reset codes now use `secrets`, are stored as password hashes, have a bounded attempt counter, and are consumed under an atomic row lock. Responses no longer disclose whether an account exists, and codes are no longer exposed in admin. |
| 2 | High | Per-process production cache broke security and job state | The generated production settings now use a file-backed shared default cache across local Gunicorn workers, while retaining an explicit local-only alias. JWT fallback stores are stable per configuration. Documentation directs multi-host deployments to Redis or another shared backend. |
| 3 | High | Public detailed health data and unbounded fake history | Detailed health views require staff access unless explicitly configured public. Public liveness is dependency-free, error responses no longer expose exception text, CSRF bypasses were removed, and the fake history endpoint now returns `501` until real storage exists. |
| 4 | High | Property filters materialized unbounded querysets | Python property filtering now counts the candidate queryset once and rejects requests above `max_property_filtering_results` (default `2000`) before materialization. Configuration validation and regression coverage were added. |
| 5 | High | Broken and incomplete test/CI gate | Duplicate test-app registration was removed, stale security and scaffold tests were repaired or deleted, registry isolation was fixed, CI now runs the full pytest suite, and the matrix tests supported Django 5.0 and 5.2 versions without dependency replacement. |
| 6 | Medium | Standard list pagination ignored `max_page_size` | Offset is normalized to zero or greater and limit is normalized to `1..max_page_size`, with explicit `None` handling. Both in-memory and database-backed list paths use the bounded values. |
| 7 | Medium | MFA recovery and SMS behavior were unsafe | Backup codes are hashed, checked atomically, and consumed once. TOTP uses the configured validity window. SMS challenges use Django's shared cache, constant-time comparison, and bounded attempts; missing providers now fail closed unless explicit development logging is enabled. |
| 8 | Medium | Nested-operation public import had a circular dependency | The mutation exception import is deferred at its only point of use, so the documented fresh-process nested import succeeds without expanding the module structure. |
| 9 | Medium | Documented management commands could not load | `render_pdf` imports its helpers from their real modules. `setup_security` no longer has a file/package collision and uses the current security module. The benchmark command and its documentation were removed because the referenced benchmark package does not exist. |
| 10 | Medium | Task listing filtered after loading and returned expired rows | Ownership, schema metadata, status, and expiry are filtered in the database. Limits are bounded and applied in SQL. Composite indexes were added for owner/status plus creation-time access paths. |
| 11 | Low | Log tail loaded the entire file | The endpoint validates `1..5000` lines and uses `collections.deque(maxlen=n)`, keeping memory proportional to the requested tail size. Internal read errors now return a generic response. |

## Query and runtime performance changes

- Standard GraphQL lists cannot bypass `max_page_size`.
- Task queries now use database predicates and SQL slicing instead of loading a
  user's complete task history into Python.
- Task indexes support the common owner/status and newest-first query paths.
- Property filters reject oversized candidate sets before evaluating Python
  properties or building a large `pk__in` clause.
- Detailed health GraphQL requests reuse one comprehensive report rather than
  recomputing it for each requested health field.
- Log tailing has bounded memory use.
- JWT refresh-store construction is cached by effective configuration.

These are path-level improvements rather than synthetic benchmark claims. The
removed benchmark command had no implementation to execute.

## Additional correctness repairs

- PEP 604 optional annotations such as `time | None` now map to the correct
  GraphQL scalar.
- Metadata template extraction uses patchable shared imports and no longer
  defeats test or application overrides with duplicate local imports.
- Class-level Excel template metadata and dynamically declared Django test
  models are isolated correctly between tests.
- Generated production entrypoints honor migration, static collection, ASGI,
  WSGI, worker, timeout, and bind configuration.
- New migrations hash existing MFA backup codes and add task query indexes.

## Verification

| Check | Result |
| --- | --- |
| Full `pytest -q` | **1456 passed**, 10 skipped, 2 warnings, 3 subtests passed in 549.57s |
| Django CI runner | **417 passed**, 4 skipped in 9.793s |
| Former order-dependent failures, in original order | **4 passed** |
| Django system check | No issues |
| `makemigrations --check --dry-run` | No changes detected |
| Runtime import sweep | 637 modules imported, 0 failures |
| Management command loading | `render_pdf` and `setup_security` load; dead benchmark command absent |
| Compile check | Runtime library and tests compile |
| Git whitespace check | Clean |
| Bandit medium/high scan | 0 high; 1 medium/low-confidence false positive for a request that already supplies a timeout |

The two pytest warnings come from tests that intentionally override Django's
`DATABASES` setting.

The scaffold template namespace is excluded from direct import and compile
checks because it contains `{{ ... }}` placeholders and becomes valid Python
only after rendering.

## Deployment and test limits

- Verification used Python 3.11, Django 5.2, SQLite, and Windows.
- PostgreSQL-specific execution, Redis behavior, multi-host cache behavior,
  browser UI behavior, and sustained production load were not exercised.
- The file-backed cache is shared across processes on one host. Multi-host
  deployments must configure Redis or another networked shared cache.
- Python property filters remain suitable only for bounded candidate sets.
  Large datasets should use database fields, annotations, or custom SQL-backed
  filters.
