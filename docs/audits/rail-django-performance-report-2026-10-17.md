# Rail Django cache-free GraphQL performance implementation

Date: 17 October 2026. Starting revision:
`9d4b6baee8e68de0228d37b32aa74bee393dd1cc` on `main`, initially clean.
The final implementation is an uncommitted working-tree change against that
revision. This report supplements the historical audit and implementation status;
it does not replace their security findings or release gates.

## Outcome and scope

Implemented selection-aware relation loading, batched nested-set preflight
reads, eager mutation response loading, reduced pagination/property-sort SQL,
and operation-wide complexity analysis. No result, permission, tenant, AST, or
query-plan cache was introduced. No dependency declarations, application models,
database migrations, or scaffold settings were changed.

The durable PostgreSQL HTTP comparison reduced a 50-row nested query from 202 to
3 SQL statements and median latency from 176.740 to 64.200 ms, a measured 63.7%
reduction for this workload. A 10-object bulk update with selected FK/M2M output
fell from 61 to 43 statements and 84.366 to 65.591 ms, a 22.3% reduction. These
are local synthetic results, not estimates of achat production performance.
Already-efficient two-query controls were sometimes slower, as detailed below.

All changes are in rail-django. Achat API code and application data were not
modified. Its checkout remained at `a1d97f3` with the pre-existing untracked
`docs/directive.md`. PostgreSQL verification used a new isolated cluster, not
achat's database. The current framework dependency in an application must load
this implementation before the application can benefit; no package publication
or deployed worker restart was performed.

## Implementation and evidence

### PERF-01: selection-aware loading across payloads

`QueryAnalyzer.analyze_query` in
`rail_django/extensions/optimization/analyzer.py` now derives model-relative
selection paths from actual GraphQL return types. This fixes items-only pages
whose relation planning previously depended on a selected `pageInfo` sibling.
It follows supported `items/edges/node/object/objects` wrappers, handles aliases,
fragments and include/skip directives, and maps camelCase relation names to
Django field names. The raw requested-field contract is retained.

Nested prefetch paths continue beyond the first collection and respect
`max_prefetch_depth`. Redundant prefixes are removed. Concrete column selections
use Django field attribute names, including custom database-column fields;
unknown computed dependencies disable narrowing instead of triggering one
deferred read per object. Private helper callers retain the old default path
normalization through optional keyword-only parameters.

Evidence: the 50-row items-only workload fell from 201 SQL statements to 2.
Regression cases cover ordinary/superusers, fragments, aliases, directives,
computed fields and prefetch depth 0/1. The existing list path remains two SQL
statements under the same non-tenant fixture.

### PERF-02: batch only preflight reads in nested set

`NestedOperationHandlerBase._resolve_related_instances` in
`rail_django/generators/nested/handler.py` resolves unique IDs with a scoped
`in_bulk` read, then performs ordered access and tenant checks for every object.
M2M set targets and reverse-FK set removals/targets use it. Custom individual
lookup overrides, duplicate IDs and malformed coercion retain individual lookup
behavior. Missing or denied children still fail before writes.

Individual validation, saves, signals and the existing atomic block remain.
Tests verify save signals for each child, tenant-filtered missing objects,
mixed allowed/denied inputs, duplicate object identity, custom overrides, and
rollback/commit-callback suppression after a later validation failure.

The 100-child removal workload fell from 203 to 104 statements. It still makes
100 validated writes. Interleaved connect/disconnect/update and bulk-update
write lookups were not blanket-batched: a preceding hook can change the next
object or its scope. SQL bulk writes would also bypass required model hooks.
That proposed shortcut was rejected on compatibility and correctness grounds.

### PERF-03: single-object and mutation output relation loading

`generators/queries/list.py` applies the existing optimizer before the single
query's `.get()`, after the custom queryset resolver. `QueryOptimizer.optimize_results`
in `extensions/optimization/optimizer.py` uses Django's
`prefetch_related_objects` on saved response instances. The shared
`generators/mutations/utils.py::_resolve_mutation_output` resolver is attached
to create/update pipeline `object` fields and bulk-create/update `objects`
fields in `generators/pipeline/factories/{create,update}.py` and
`generators/mutations/bulk.py`. It preserves the original root instances and
does not reread or replace them. Delete and custom method outputs are unchanged.

While expanding eager loading, review found unscoped prefetched shortcuts in
`generators/types/objects.py`. M2M, reverse and generic collection returns, plus
generic counts, now pass through tenant scope. A regression verifies that an
organization list cannot expose another tenant's nested projects. This is a
security correction: affected callers may receive fewer rows or tenant errors.
It can require extra SQL for tenant-scoped collections; no universal constant
query-count promise is made for those schemas.

Profiling showed repeated full multitenancy-settings construction on hot paths.
`extensions/multitenancy/applicator.py` now reads only enabled/default-field
settings first and avoids parsing the remaining settings for models without a
tenant field. It uses the same coercion and configuration helpers and stores
no permission or tenant decision. A first 50-row control had regressed to about
11–12 ms; this refinement brought it to about 8 ms. It remains slower than the
roughly 6.7 ms baseline control, so the residual cost is reported, not hidden.

### PERF-04: avoid unused count/item reads and deferred property fetches

`generators/queries/list.py` requests property ordering without a total count
for ordinary lists. `QueryOrderingHelper._apply_property_ordering` in
`generators/queries/base.py` clears deferred columns and reads at most the
existing candidate cap plus one detection row when a count is unnecessary.
The capped subset, ordering and paginated exact-total semantics are retained.
Full-row loading can increase bytes transferred for wide models.

`generators/queries/pagination.py` detects whether items were selected. Exact
metadata-only requests retain totals and page clamping while avoiding unused
item SQL. Skip-count metadata uses an offset existence query. A selection of
`items { __typename }` still produces the proper item cardinality. Tests assert
exact totals, a page-999 clamp, next-page flags and capped property sort results.

### PERF-05: validate operation limits once per execution

The new `rail_django/core/execution.py::RailExecutionContext` is the default in
`graphql/views/multi_schema/view.py` when no explicit/class execution context is
configured. It prepares exact stock `QueryComplexityMiddleware` instances once
per query execution. Successful checks leave that operation's per-field chain;
failed checks retain the middleware position and matching root-field errors.
Other authentication, object/field checks, rate limiting and middleware remain.
Subclasses/custom execution contexts retain their existing resolver behavior.
No operation decision survives into the next execution.

`core/middleware/performance.py::validate_operation` and
`core/performance.py::validate_query_limits` reuse the existing AST and populate
metrics from the same analysis instead of making a redundant preliminary pass.
Tests compare real complexity rejections and full formatted alias errors with
the legacy execution context; verify mixed public/protected fields, directives,
an unhashable denying field middleware, a changed next-request decision, and
explicit/class execution-context overrides. The 20-alias workload makes one
validation instead of 20.

Custom analyzers overriding `validate_query_limits` must accept the new optional
`metrics` keyword when installed on the stock checker. Operation prevalidation
now precedes root-resolver timing; complete HTTP timing still includes it.

## Measurement method

Evidence is retained in
[the results JSON](rail-django-performance-results-2026-10-17.json).
The opt-in reproducible workloads are in
`tests/benchmarks/graphql_workloads.py`; actual HTTP coverage/measurement is in
`tests/integration/test_graphql_http_performance.py`. Normal collection does
not run timing loops in the benchmark file. Timings have no flaky pass threshold;
regression tests assert outputs, access decisions, hooks and SQL counts.

Environment: Windows, PowerShell, Python 3.11.0, Django 5.2.18, Graphene 3.4.3,
graphql-core 3.2.3, PostgreSQL 16.2. A second isolated dependency environment uses
graphql-core 3.2.13. The baseline is a Git archive of the starting revision;
benchmarks assert the imported framework path so the baseline cannot silently
execute the edited checkout.

The owned cluster listens only on `127.0.0.1:55439`, with synthetic database
`rail_perf` and test database `test_rail_perf_iterations`. Initial iterative
microbenchmarks used `fsync=off`. The cluster was restarted and `fsync=on` was
verified before repeating the complete before/after workload and HTTP comparison
shown below. Do not mix those two durability groups when interpreting writes.
Microbenchmark write cases run inside pytest's outer rollback transaction;
durable HTTP mutations exercise actual per-request commits.

Read fixtures: 1,000 Posts, 10 Categories and 3 Tags, one tag per post, page
sizes 10/50. Schemas are already built. Microbenchmarks use 3 warmups and 30
samples, except the 20-root-alias analysis case with 5 warmups and 100 samples.
`schema.execute` timings include parsing, validation, resolution and GraphQL
completion; they exclude HTTP/JSON and schema startup. Setup/reset SQL is outside
the timing capture.

HTTP fixtures: 1,000 Posts sharing one Category and one Tag, a real JWT
superuser and a denied user, the actual multi-schema HTTP view and middleware.
DummyCache, permission-cache disabled, result caching disabled, tenancy disabled
for this non-tenant workload; ABAC, rate limiting and query logging disabled
only within the fixture. Authentication, model and field checks remain enabled.
Three warmups precede 100 requests per scenario. A separate four-client pass
performs 100 reads. Each request opens a requests session without environment
proxies; test-only SQL timing headers come from `connection.execute_wrapper`.
This Django development live server is not a production worker/proxy benchmark.

### Final durable HTTP comparison

| Workload | Baseline SQL | Final SQL | Baseline median ms | Final median ms |
| --- | ---: | ---: | ---: | ---: |
| 50-row items-only page, title + category.name + tags.name | 202 | 3 | 176.740 | 64.200 |
| Bulk update 10 with the same selected relations | 61 | 43 | 84.366 | 65.591 |

The corresponding median accumulated SQL times were 37.001 → 3.236 ms and
14.171 → 10.588 ms. SQL time is included in request latency, not an additional
component to add. Four local clients completed 100 reads in 13.418 → 3.538
seconds, or 7.453 → 28.261 requests/second. Those rates describe only this local
fixture and are not a service capacity guarantee. No percentile claims are made.

### Final durable in-process comparison, including slower controls

| Workload | SQL before → after | Median ms before → after |
| --- | --- | --- |
| Items-only page, 10 rows | 41 → 2 | 22.045 → 4.127 |
| Items-only page, 50 rows | 201 → 2 | 91.390 → 8.536 |
| Ordinary list, 10 rows | 2 → 2 | 3.430 → 3.810 |
| Ordinary list, 50 rows | 2 → 2 | 6.678 → 8.007 |
| Page with pageInfo, 10 rows | 2 → 2 | 4.404 → 4.351 |
| Page with pageInfo, 50 rows | 2 → 2 | 6.413 → 8.023 |
| Single object with FK/M2M output | 3 → 2 | 2.730 → 2.870 |
| Reverse set, 1 removed child | 5 → 5 | 1.686 → 1.848 |
| Reverse set, 10 removed children | 23 → 14 | 11.309 → 6.985 |
| Reverse set, 100 removed children | 203 → 104 | 105.733 → 50.419 |
| Bulk update output, 10 objects | 52 → 34 | 29.717 → 20.566 |
| Bulk update output, 50 objects | 252 → 154 | 138.437 → 81.981 |
| Computed-property order, 200 rows/cap 100/output 50 | 102 → 1 | 38.584 → 2.111 |
| Metadata only, default auto count with exact fallback | 3 → 2 | 2.078 → 1.508 |
| Metadata only, skip count | 1 → 1 | 1.522 → 1.275 |
| 20 root aliases, operation analysis | 20 → 1 validations | 6.900 → 5.481 |

The metadata workload name `metadata_exact` in raw results uses default auto
count mode, including its estimator lookup/exact fallback. The separate
regression explicitly using `countMode:"exact"` performs one count after the
change. The property-sort workload tests a known deferred-column pathology,
not arbitrary expensive properties. A lower statement count did not make the
single-object median faster in this sample. Two-query list controls have about
1.3–1.6 ms added cost at 50 rows from planning and restored tenant checks.
These measurements do not establish the full distribution or a universal gain.

### Measurements and checks at each iteration

All rows here use the initial `fsync=off` cluster and independent selected
regression groups. Counts overlap; do not add them together.

| Iteration | Selected regression result | Same-workload evidence |
| --- | --- | --- |
| 1 / PERF-01 | 21 passed, 2.19 s | Items-only page 50: 201 → 2 SQL, 100.492 → 7.716 ms |
| 2 / PERF-02 | 25 passed, 3.83 s | Reverse-set 100: 203 → 104 SQL, 109.387 → 61.343 ms |
| 3 / PERF-03 | 34 passed, 6.27 s; tenancy refinement 22 passed, 3.75 s | Bulk-output 50: 252 → 154 SQL, 158.776 → 93.318 ms; list-50 refinement 7.997 ms |
| 4 / PERF-04 | 30 passed, 6.65 s | Computed property sort: 102 → 1 SQL, 46.863 → 2.068 ms |
| 5 / PERF-05 | 26 passed, 1.31 s | 20 aliases: 20 → 1 validations, 7.257 → 5.745 ms |

The first bulk-output capture exceeded Django's 9,000-entry debug query log and
produced invalid counts; it was discarded and rerun with `reset_queries()`
before each sample. The table/results use the corrected capture. A benchmark
fixture initially used numeric mutation IDs that hit existing permissive
global-ID decoding; it was changed to supported Relay global IDs. The existing
numeric-ID ambiguity was not changed or fully audited by this performance work.

## Verification commands and outcomes

All commands run in PowerShell. `python` below denotes an isolated interpreter,
not an alteration of the user's installed application dependencies. Working
evidence root: `%TEMP%/rail-graphql-performance-20261017-5e54`. The inherited
test interpreter is `%TEMP%/rail-implementation-venv/Scripts/python.exe`; the
clean dependency interpreter is
`%TEMP%/rail-implementation-ea41f5fb42634185beacc9682a29825d/package-env/Scripts/python.exe`.

PostgreSQL settings in the temporary root import
`rail_django.config.test_settings`, override only DATABASES to the owned cluster,
and disable auth/contenttypes migrations to match the synthetic unmigrated
test-app setup. Network guards on PYTHONPATH block outgoing Python sockets;
HTTP verification permits only loopback port 55440 plus internal test wakeups.
These Python guards are a verification aid, not an operating-system sandbox.

```powershell
$work = Join-Path $env:TEMP 'rail-graphql-performance-20261017-5e54'
$env:DJANGO_SETTINGS_MODULE = 'perf_settings'
# PYTHONPATH: the socket guard, temporary settings root, and tested source root.
$env:PERF_LABEL = 'final-durable'
$env:RAIL_PERF_SOURCE_ROOT = 'E:\Projects\libraries\rail-django'
$env:RAIL_PERF_OUTPUT_DIR = "$work\durable-final"
python -m pytest -c pytest.ini tests/benchmarks/graphql_workloads.py --reuse-db -q -s --tb=short -p no:cacheprovider

$env:RAIL_PERF_HTTP_SAMPLES = '100'
$env:RAIL_PERF_HTTP_OUTPUT = "$work\final-http-durable-refined.json"
python -m pytest -c pytest.ini tests/integration/test_graphql_http_performance.py --reuse-db --liveserver=127.0.0.1:55440 -q -s --tb=short -p no:cacheprovider
```

The baseline runs use the same workload files copied outside the checkout,
baseline cwd/PYTHONPATH, its `pytest.ini`, and an asserted baseline import path.
Final benchmark harness: 5 passed in 8.73 s; baseline: 5 passed in 17.52 s.
Final durable HTTP: 1 passed in 20.13 s; baseline: 1 passed in 43.23 s.
Suite runtimes are not substitutes for the individual measurements.

| Check | Exact command and relevant settings | Outcome |
| --- | --- | --- |
| Combined pytest | `python -m pytest --ignore=tests/integration/test_graphql_http_performance.py -q --tb=short -p no:cacheprovider`; inherited environment, `DJANGO_SETTINGS_MODULE=rail_django.config.test_settings`, outbound socket guard | 1,524 passed, 10 skipped, 2 warnings and 3 subtests passed in 682.61 s |
| Unit marker after fixture correction | `python -m pytest -m unit -q --tb=short -p no:cacheprovider`; inherited environment/test_settings | 891 passed, 2 skipped, 643 deselected in 32.75 s |
| Complete PostgreSQL integration | `python -m pytest -m integration --reuse-db --liveserver=127.0.0.1:55440 -q --tb=short -o faulthandler_timeout=90 -p no:cacheprovider`; clean environment, `DJANGO_SETTINGS_MODULE=perf_checked_settings` | 244 passed, 1,292 deselected in 144.85 s |
| Final PostgreSQL regression handoff | `python -m pytest tests/integration/test_graphql_performance.py tests/unit/test_operation_execution.py tests/unit/test_audit_regressions.py tests/unit/test_audit_contracts.py tests/unit/test_pipeline_transactions.py --reuse-db -q --tb=short -p no:cacheprovider`; clean environment/perf_checked_settings | 44 passed in 3.13 s |
| Additional response-identity regression | `python -m pytest tests/integration/test_graphql_performance.py -q --tb=short -p no:cacheprovider`; inherited environment/test_settings | 18 passed in 1.75 s |
| Django runner | `python -m django test tests.unit --noinput`; inherited environment, `DJANGO_SETTINGS_MODULE=rail_django.config.framework_settings` | 417 tests, OK, 4 skipped, 6.511 s; no system-check issues |
| Wheel and source archive | `python -m build --no-isolation --outdir <work>/dist` from an isolated copy of current package sources, `SETUPTOOLS_SCM_PRETEND_VERSION=0.1.8.dev1` | Both built; the version is a local verification override, not a release |
| Installed-wheel imports and tests | `python -m pip install --no-deps --target <work>/wheel-import <work>/dist/rail_django-0.1.8.dev1-py3-none-any.whl`; then `python -m pytest -c <checkout>/pytest.ini <checkout>/tests/unit/test_operation_execution.py <checkout>/tests/unit/test_optimization_prefetch_paths.py -q --tb=short -p no:cacheprovider` outside checkout, wheel target first on PYTHONPATH | Explicit wheel import-path assertion passed; 10 tests passed in 0.16 s with graphql-core 3.2.13 |
| Schema comparison | Same `build_schema(schema_name="compatibility_capture", apps=["test_app"], models=["test_app.Category", "test_app.Product"])` introspection script in baseline/final processes, JSON sorted, SHA-256 comparison | Identical snapshot; hash below |
| Focused formatting | `python -m black --check rail_django/core/execution.py tests/unit/test_operation_execution.py tests/integration/test_graphql_performance.py tests/integration/test_graphql_http_performance.py tests/benchmarks/graphql_workloads.py tests/unit/test_audit_regressions.py tests/unit/test_audit_contracts.py tests/integration/test_subscription_transport.py` | 8 files unchanged |
| Whitespace/syntax | `git diff --check`; Python `ast.parse` on changed modules | Passed |
| Rail Framework validator | `python <skill>/scripts/rail_skill.py validate --config <prior-work>/rail-sources.json --project E:/Projects/libraries/rail-django --base 9d4b6bae --json` | Exit 2, no errors; heuristic self-matches and stale accepted manifest, explained below |

These runs overlap. The combined run preceded the last real-limit/response-identity
assertions and portable test correction; the subsequent unit and PostgreSQL
handoff runs cover those final changes. The live HTTP test was excluded only
from the outbound-blocked combined SQLite run and passed separately in the
PostgreSQL suite and both baseline/final HTTP benchmarks.

The first complete PostgreSQL attempt was stopped while test-database TRUNCATE
waited on an idle audit-insert transaction. A temporary settings variant,
`perf_checked_settings`, adds libpq `lock_timeout=5000` and
`statement_timeout=60000` to the same isolated database. The bounded retry
completed, exposing one SQLite-only test query: 243 passed and 1 failed in
146.98 s. The unchanged archived baseline reproduces that failure (1 failed in
1.56 s). `TestDatabaseOperationsAdvanced.test_database_migration_compatibility`
now uses `connection.introspection.table_names()` instead of `sqlite_master`.
Its SQLite check passed, and the final complete PostgreSQL run passed all 244
tests. This is a test portability correction, not a runtime performance fix.
The first cleanup wait did not recur; its lifecycle cause remains unproven.

Combined-suite warnings come from the existing control-center tests overriding
DATABASES. The ten skips remain gaps in those tests; they are not ten verified
features. The Django runner discovers unittest cases and does not replace the
larger pytest function-based coverage.

The first unit run found two Mock queryset fixtures missing a chainable
`.defer()` return. Those fixtures were corrected; the focused query/optimizer
checks then passed 43 tests. New source and test files plus the CI's focused
audit files pass Black. Tracked Python edits were formatted by changed ranges
to avoid unrelated churn. Black's range formatter cannot process the existing
mixed-EOL/minified view module without changing unrelated try/finally layout;
that file retains its existing layout and parses successfully. `git diff --check`
passes. No broad cosmetic reformat was performed.

The reused clean environment initially lacked Promise source files despite
retaining its installed metadata. Only that disposable environment's existing
`promise==2.3` was reinstalled. The build interpreter needed `wheel==0.45.1`,
installed only into that disposable venv. No project dependency was changed.
`pip check` in the clean environment reports no broken requirements.

## Compatibility, deployment and rollback

| Change | Classification and consumer risk | Evidence and release requirement |
| --- | --- | --- |
| PERF-01 loading | Internal SQL change; custom fields/managers can observe different load order; deeper prefetch may use more memory | SQL/response tests; replay custom fields and relation names at real cardinality |
| PERF-02 preflight batching | Internal intent, observable read timing; save/signal order retained; custom lookup/duplicate fallback | Denial, tenant, signal, validation rollback and override tests; verify application-specific guards |
| PERF-03 response loading | Internal intent; serialized relation reads occur earlier, outside the existing write transaction | Bulk output regression and HTTP write/read checks; test custom payloads and side effects |
| Prefetched tenant scope | Security correction requiring documented behavior change | Cross-tenant nested test; review tenant-aware outputs and counts; do not restore leakage to regain speed |
| PERF-04 counts/rows | Internal SQL change; full columns for properties can increase row bytes | Totals/clamping/typename/cap tests; profile wide models and custom properties |
| PERF-05 execution context | Additive class plus changed default execution behavior; custom analyzer metrics signatures and timer coverage can differ | Legacy error comparison, custom contexts, real HTTP, graphql-core 3.2.3/3.2.13; test custom middleware order |

The generated Category/Product schema introspection is byte-identical between
baseline and final (SHA-256
`f9fc503237537b4fe27f1ee81ee946e2069eb084ecec3610f9580b400fec089e`).
This covers those generated contracts, not every application schema. No field,
argument, enum, nullability, import removal or default-setting change is
intended. Passing framework tests does not guarantee all downstream contracts.

No data migration or scaffold rewrite is required. New generated applications
already use the framework HTTP view and receive the default execution context.
Existing consumers using that view need the updated package and worker restart;
custom Graphene entry points keep their own context unless they explicitly opt
in. The new canonical guide is
`rail_django/docs/operations/graphql-performance.md`, linked from the docs index
and security/performance pages.

Release in small reviewable units corresponding to PERF-01 through PERF-05,
keeping the tenant correction with the affected eager-loading paths. Require
the regression gates, schema diff, representative operation replay and supported
runtime CI before publication. Roll out to a canary; compare SQL, HTTP latency,
errors, memory and database locks. Keep an immutable prior artifact for rollback.
A rollback that reinstates unscoped tenant collections is unsafe: retain the
tenant patch or disable affected automatic prefetch paths while investigating.
No publication, GitHub synchronization, or production deployment was done here.
The owned PostgreSQL cluster was stopped after verification; temporary evidence
and isolated database files were retained for inspection.

## Remaining limits and deliberately rejected changes

- Achat-specific GraphQL operations, data distributions, authorization policies,
  deployment middleware, and PostgreSQL indexes/plans were not benchmarked. The
  user allowed PostgreSQL verification; synthetic framework models avoid touching
  business data. Production benefit remains to be measured.
- No Python 3.12, alternative Django series, graphql-core 3.3, MySQL, Redis,
  production worker/proxy, large-fanout memory profile, or lock-contention load
  test was completed. Local supported-version observations are not the full CI
  matrix. Cold schema/startup cost was not the target of this steady-state work.
- Mutation validation queries and per-object writes still scale with the number
  of inputs. Hook/query-heavy application properties need their own workload.
  Offset pagination and exact counts retain their existing database costs.
- Result/permission caching, unchecked SQL bulk writes, application-specific
  indexes, speculative async conversion, a new optimizer framework, and global
  schema rewrites were rejected. None is justified by these measured paths.
- The Rail Framework skill validator returned no errors, heuristic self-duplicate
  warnings and incomplete freshness against its accepted manifest. It compares
  framework source against the same configured framework repository, producing
  self-matches including existing methods in changed files. They were reviewed
  as such; it is not a completed fresh skill snapshot. The installed skill was
  not rewritten to suppress that result.

Keep these unresolved gates visible when reviewing or releasing the changes.
