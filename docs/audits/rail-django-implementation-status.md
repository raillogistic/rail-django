# Rail Django implementation status

This records implementation of the October 2026 [improvement plan](rail-django-improvement-plan.md). The [audit](rail-django-audit.md) remains a historical account of revision fbca6deb21d93c347e47af86fbcdd2d8e5844fa3. Changes were implemented and verified locally; no release, tag, production migration or application-data repair has been performed.

## Implemented corrections

| Finding | Implementation | Compatibility effect |
| --- | --- | --- |
| RD-001 | Bypass resolver result caching; retain decorator signature, queryset optimization and monitoring | Resolver authorization runs every time; cache-dependent latency changes |
| RD-002 | Authorize removed/target children before reverse set, use validated saves inside atomic | Denied child changes fail; detach save hooks now execute |
| RD-003 | Remove scope-expanding retry, sanitize database evaluation errors in both list modes | Database failures return an error instead of broader results |
| RD-004 | Preserve trusted request/JWT context; require authenticated membership authorizer for header/subdomain selection; allow empty header to disable fallback | Header-only deployments must migrate |
| RD-005 | Keep CSRF checks for retained session identity; record validated explicit header-token provenance | Dummy/stale bearer headers do not exempt session requests |
| RD-006 | Use the same model/owner/shared queryset for saved-filter ID and name | Private and wrong-model numeric IDs no longer apply |
| RD-007 | Invalidate schema/generator state while retaining builder identity and explicit custom mutations; synchronize schema-cache version reads/fills with rebuilds | Re-registration actually changes the served schema; concurrent cache fills cannot retain old fields under a new version |
| RD-008 | Import real candidate modules and expose internal dependency errors | Previously missed modules may load; collisions must be checked |
| RD-009 | Evaluate database discovery inside its error boundary, retry pending registration after migration, provide explicit required-registry mode | Optional discovery recovers; required mode fails closed |
| RD-010 | Separate group registration from GraphQL serialization; bind schema-specific ASGI consumers; refresh identity, policies and tenant checks per event; capture committed signal snapshots and clean groups | Subscriptions can deliver; existing protocol and field names retained |
| RD-011 | Roll back a returned abort context as well as raised errors | Failed custom mutations stop persisting partial database writes |
| RD-012 | Set Django minimum to 5.2.18; update library/scaffold/achat declarations, docs and CI | Django 5.0/5.1 support removed as an explicit security baseline change |
| RD-013 | Gate publication on CI for the same SHA, verify an existing tag's commit, build/import artifacts before tagging | Release workflow timing changes; no local publication |

Clean-environment verification also exposed a PDF guard that allowed wkhtmltopdf without explicit unsafe-fetch opt-in when no URL fetcher was available. The guard now requires the opt-in independently of the WeasyPrint installation. A direct no-fetcher regression prevents subprocess execution in the denied case.

The final installed-package smoke test found an invalid scaffold mutation path, users.apps.mutations.UsersMutations. New projects now use apps.users.mutations.UsersMutations, matching their AppConfig package. An installed-wheel project successfully imports the extension and exposes upsertUserTableConfig. This is an additive schema correction for newly generated projects; review those user mutations when adopting the updated template. Existing application settings are not rewritten. WebSocket malformed initialization payloads and complete IDs now close with protocol code 4400, covered by real transport regressions.

A final RD-007 concurrency check confirmed that get_schema_instance could store an old schema under a concurrently advanced version. Holding the retained builder lock across cache lookup/build/version capture fixes the shared race. The threaded regression fails against the audited getter and passes with the synchronized getter; no cross-worker coordination claim follows from this process-local fix.

Migration, authentication, tenant callback, subscription and rollback contracts are documented in [audit-security-update.md](../../rail_django/docs/operations/audit-security-update.md).

## Achat integration

The authorized consumer baseline is 915df7a69d99b66de2d33f435a940fc1ddd4e824.

- Updated the Django floor and ASGI routes to schema-bound .as_asgi() callables with origin validation.
- Disabled the unused broad subscription configuration. Enable it only with an explicit model allowlist and a tested client.
- Added HTTP regressions for session CSRF and valid header tokens, plus a real-endpoint frontend authentication check using the existing auth helper.
- Added requirements/local.txt for testing the sibling editable checkout without changing the production immutable Git pin.
- Preserved pre-existing and concurrent changes elsewhere in the consumer/frontend.

The production rail-django requirement still names the existing release. It must be advanced to the reviewed immutable release containing these fixes after publication; no nonexistent release or uncommitted Git SHA was invented.

## Verification completed

All runtime checks used disposable environments and synthetic databases. PostgreSQL 16 was started on loopback port 55437 with a new data directory; no existing PostgreSQL instance or production database was used. Achat ran from a Git archive with source overlays, without copying environment/credential/data files. The real HTTP server used loopback port 55438 and a disposable synthetic account/database.

| Check | Observed result |
| --- | --- |
| Full framework pytest on Python 3.11.0 / Django 5.2.18 / inherited GraphQL versions | 1,492 passed, 10 skipped, 2 warnings and 3 subtests passed in 627.11 seconds |
| Django runner tests.unit | 417 run, 4 skipped, OK in 5.926 seconds |
| Final clean resolved dependency environment, unit marker | 884 passed, 2 skipped, 625 deselected in 28.95 seconds |
| Final focused audit/contract/transport regressions | 21 passed in 4.33 seconds |
| PostgreSQL audit/contract/pipeline/transport checks | 23 passed in 5.06 seconds, using a reusable isolated test database |
| Real Channels ASGI tests | Committed delivery, rollback suppression, revocation, multi-operation cleanup, two-tenant separation and deleted-ID snapshot checks pass |
| Final wire-format/transport/generator checks | 12 passed; JSON-compatible snapshots restore model field types and preserve datetime precision |
| Achat HTTP regressions | 2 passed against the modified framework and isolated PostgreSQL |
| Frontend real-endpoint authentication | 2 passed against the isolated achat server |
| Final handoff audit/contract/pipeline/transport/scaffold/registry checks | 70 passed in 4.41 seconds, including malformed WebSocket messages and concurrent cache replacement |
| Wheel and sdist | Final artifacts built as 0.1.44.dev0, installed into the disposable package environment and imported outside the checkout; rail-admin created a fresh project whose system check and configured user mutation schema exposure passed |
| Bounded Django ASGI body check | With a 512-byte limit, a 100-byte synthetic body returned 200 and a 1,024-byte body returned 400; no large upload or upstream proxy was exercised |
| Representative schema introspection before/after | Identical canonical JSON SHA-256 F9FC503237537B4FE27F1EE81EE946E2069EB084ECEC3610F9580B400FEC089E for Category/Product fixture |
| Rail Framework skill validator | No errors/warnings; incomplete because the maintained skill manifest describes the earlier framework snapshot |

The full run precedes the final PDF guard and extra transport/token regression additions. The PostgreSQL run covers those changes; the final handoff run covers the subsequent malformed-envelope, scaffold and schema-cache synchronization changes. Do not add these counts together: the runs overlap.

Generated events now use wire-compatible scalar snapshots (including decimal/date/file/binary field conversions where supplied by Django), and publication restores model field types before GraphQL serialization. This avoids relying on an in-memory channel layer's ability to retain Python objects. A live Redis service was not exercised.

The complete achat run executed 431 tests and reported two failures and three errors. The full comparison against the audited framework also reproduced all five existing failures: supplier spending fixtures attempt invalid post-approval line creation (two errors), an offer-comparison HTTP assertion has no data key, the supplier-manager permission fixture lacks change_supplier, and the payment role-permission assertion fails in the complete suite. The old framework additionally fails the newly added invalid-header/session-CSRF regression, as intended. The old/new full runs took 437.179/454.979 seconds. These results establish no new failure in this consumer suite, but are not a green consumer release gate.

An earlier broad achat run was invalidated when concurrent verification commands shared a disposable test-database name. Later runs use distinct names. A clean temporary environment also required repair of an incomplete promise installation before its successful rerun. These harness/environment failures are not treated as framework defects.

After adding schema-cache synchronization, the clean unit run exposed a synthetic builder Mock without its production RLock (one failure, 883 passes). The existing fixture now supplies the lock; this did not require a production fallback that would bypass synchronization.

## Reproduction and evidence

Verification ran in PowerShell on Windows with Python 3.11.0. The inherited environment used Django 5.2.18, Graphene 3.4.3, graphql-core 3.2.3, graphene-django 3.2.3, pytest 9.0.2, Channels 4.3.2 and Daphne 4.2.1. The clean package environment resolved graphql-core 3.2.13, pytest 9.1.1 and Daphne 4.2.3 alongside the same Django/Graphene/Channels versions. These are local observations, not a completed support matrix.

Temporary evidence is under C:/Users/khale/AppData/Local/Temp. The disposable working root is rail-implementation-ea41f5fb42634185beacc9682a29825d; the inherited-package virtual environment is rail-implementation-venv. Full resolved clean-environment versions are in rail-implementation-package-freeze-final.txt. The temporary PostgreSQL cluster was stopped after verification. Its settings and data directory remain isolated for inspection.

| Invocation | Settings/context and evidence log |
| --- | --- |
| python -m pytest -vv -rs --tb=short -o faulthandler_timeout=60 --durations=10 | Framework checkout; DJANGO_SETTINGS_MODULE=rail_django.config.test_settings; rail-implementation-full-verified.log |
| python -m django test tests.unit --noinput --verbosity 0 | Framework checkout; DJANGO_SETTINGS_MODULE=rail_django.config.framework_settings; rail-implementation-django.log |
| python -m pytest -m unit -q -rs --tb=short | Clean package environment with checkout on PYTHONPATH and test_settings; rail-implementation-clean-final.log |
| python -m pytest tests/unit/test_audit_regressions.py tests/unit/test_audit_contracts.py tests/unit/test_pipeline_transactions.py tests/integration/test_subscription_transport.py --reuse-db -q --tb=short | DJANGO_SETTINGS_MODULE=implementation_pg from the temporary root; only the owned loopback PostgreSQL cluster; rail-implementation-pg-final-code.log |
| python -m pytest tests/unit/test_audit_regressions.py tests/unit/test_audit_contracts.py tests/unit/test_pipeline_transactions.py tests/integration/test_subscription_transport.py tests/unit/test_scaffolding_templates.py tests/unit/test_registry.py -q --tb=short | Final source, test_settings and disposable SQLite; rail-implementation-final-handoff.log |
| python -m black --check tests/unit/test_audit_regressions.py tests/unit/test_audit_contracts.py tests/integration/test_subscription_transport.py | Passed; git diff --check also passed in framework and achat API |
| python -m build --outdir TEMP_ROOT/dist-final | Final wheel/sdist; rail-implementation-build-final.log |
| python -m pip install --no-deps --force-reinstall TEMP_ROOT/dist-final/rail_django-0.1.44.dev0-py3-none-any.whl; rail-admin startproject smoke_api_final | Clean disposable environment, outside source checkout; rail-implementation-package-final.log |
| python verify_installed.py; python verify_asgi_body.py | Fresh generated project with temporary root.audit.development settings, SQLite/local caches and outbound Python socket guard; rail-implementation-scaffold-final.log and rail-implementation-asgi-body.log |
| node_modules/.bin/vitest.cmd run src/test/integration/frameworkSecurity.realEndpoint.test.ts --maxWorkers=1 | Authorized frontend; only the disposable achat endpoint and synthetic account; rail-implementation-frontend-focused.log |
| python -m pip_audit --path TEMP_ROOT/package-env/Lib/site-packages --format json --output TEMP/rail-implementation-pip-audit-final.json | Final resolved package/scaffold environment; expected exit 1 for the retained Twisted advisory; rail-implementation-pip-audit-final.log |

TEMP_ROOT denotes the full disposable working root above; TEMP denotes the Windows temporary directory. PostgreSQL test settings deliberately disable auth/contenttypes migrations to support the unmigrated test fixture ordering. Achat full-run logs are rail-implementation-achat-full-verified.log and rail-implementation-achat-full-baseline-final.log; both use archived application sources, temporary root.audit.development overrides and distinct synthetic test database names. Do not run them with the application's ordinary development/production database settings. The socket guard is a Python verification aid, not an operating-system network sandbox.

## Plan completion and boundaries

| Plan items | State |
| --- | --- |
| B-01 | Local baseline, clean resolution, package/scaffold, representative schema comparison and authorized consumer replay completed; Python 3.12 and wider consumer contracts remain release gates |
| B-02 and S-01 through S-08 | Code, regression and migration changes implemented; remote release execution and deployment support-policy acceptance remain maintainer gates |
| P-01 | Related-list and child-detach measurements completed; production-cardinality list/count/export/import memory profiling remains unmeasured, with no optimization claimed |
| P-02 | Deliberately deferred under its stated acceptance rule; unsafe result caching remains disabled |
| M-01 through M-04 | Retained-builder lifecycle, discovery recovery/imports, docs, package and scaffold corrections implemented and checked locally; multi-worker production propagation remains deployment-owned |
| D-01 | Existing protocol repaired with real local transport/tenant/rollback/revocation/cleanup checks; achat remains disabled pending its own client/allowlist and production broker validation |
| D-02 | Compatibility choices and transition documented in the migration guide; release number, release publication and consumer immutable-pin rollout remain maintainer decisions |

## Performance and optional work

Subsequent cache-free query and mutation work, including isolated PostgreSQL
before/after measurements, is recorded in
[the 17 October performance report](rail-django-performance-report-2026-10-17.md).
The observations below remain the earlier audit-implementation baseline.

The related-list workload remains bounded at two SQL queries for 50 Posts with FK/M2M fields from 100 rows. A final six-run sample measured 6.974, 5.411, 4.972, 4.986, 6.350 and 4.764 ms. This is a small warm SQLite workload; it is not a claimed production speedup.

A second local SQLite workload measured the corrected reverse-set removal path for 1, 10 and 100 synthetic Product children. With an already constructed handler, ABAC disabled and an authorized superuser context, query counts were 5, 23 and 203; elapsed times were 2.102, 7.421 and 65.501 ms respectively. Each workload was measured once; setup was excluded. This demonstrates the linear lookup/validated-save cost of preserving child authorization and hooks. It does not justify reverting to unchecked bulk updates. All three workloads verified that every child was detached only after the permitted operation.

Unsafe result caching stays disabled. P-02 restoration is deliberately deferred because no public-resolver authorization contract and measured benefit justified it. Broader production-cardinality profiling and any further optimization require their own workload and behavior-equivalence evidence. No new cache engine or broad generator rewrite was introduced.

## Dependency advisory follow-up

A scan of the clean environment initially found old bootstrap pip/setuptools plus Twisted 26.4.0. Bootstrap tools were upgraded only inside that disposable environment. The remaining Twisted advisory is [CVE-2026-106454](https://github.com/twisted/twisted/security/advisories/GHSA-8pqf-f4m5-798g), whose affected range includes <=26.4.0 and has no published patched package in that record. It concerns authenticated IMAP wildcard matching. Rail Django/Achat do not expose an IMAP server in the reviewed paths, so an exploitable HTTP/WebSocket route was not established. Keep the dependency alert open pending an upstream release; do not call the whole dependency graph vulnerability-free.

## Remaining release gates

- Resolve the five consumer-suite baseline failures before treating the complete application release gate as green; their before/after comparison is complete.
- Run the configured Python 3.11/3.12 minimum/current Django matrix on CI; Python 3.12 was unavailable locally.
- Validate remote workflow permissions/event/retry behavior before publication. Local static checks are not an executed GitHub Actions release.
- Review consumer-specific tenant membership integration before enabling header selection.
- Choose and publish the release version, then advance achat's production immutable pin.
- Verify representative production broker/storage/proxy behavior. No Redis/MySQL or production-load guarantee is made.
- Validate deployment ASGI upload and upstream proxy limits together; the bounded local body check only establishes Django's configured rejection behavior.
