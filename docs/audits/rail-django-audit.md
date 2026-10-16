# Rail Django implementation and security audit

Audit date: 16 October 2026. Repository: `E:/Projects/libraries/rail-django`. Committed baseline: `fbca6deb21d93c347e47af86fbcdd2d8e5844fa3` (`fix bugs`, committed 15 October 2026). Local describe: `v0.1.43`.

Scope: read-only implementation audit and safe local verification. No fixes, dependency installations, consumer edits, database migrations against application data, tags or releases were performed. The only intended repository additions are this report and the [implementation plan](E:/Projects/libraries/rail-django/docs/audits/rail-django-improvement-plan.md). Initial working tree was clean, so the committed archive matched the source baseline inspected. All line references below refer to that revision.

## A. Executive assessment

The framework has substantial functionality and meaningful regression coverage: the complete local pytest run passed 1,474 tests, with 10 skipped. Its shared generators, permission helpers and test harness provide practical places to make small corrections. Passing those tests does not establish security or compatibility. Eleven additional behavioral checks reproduced gaps not caught by the existing suite.

The most consequential confirmed issues are conditional authorization failures: opt-in resolver caching can skip resolver permissions and collide across field arguments (RD-001); reverse-relation replacement can detach children without their update permissions (RD-002); and an unpaginated database-error fallback can discard restrictions (RD-003). The tenant header selects a scope without proving membership (RD-004), which is unsafe when applications treat the documented header-only integration as an authorization boundary. CSRF identity classification and saved-filter ID access also need correction (RD-005, RD-006).

Correctness problems include stale schemas after re-registration, import-order-dependent discovery, incomplete handling of lazy database errors, nonfunctional generated WebSocket subscriptions and a custom pipeline abort that commits earlier writes (RD-007–RD-011). The measured environment contains an affected Django release (RD-012), and the release workflow lacks an explicit test gate for the released commit (RD-013).

There are 13 prioritized findings: four high and nine medium. None is rated critical. Confidence is confirmed for the specific behavior described; this does not mean every deployment is exposed. Authorization findings include their activation conditions and limits. In particular, no production tenant breach, browser CSRF exploit, subscription event leak or large-upload denial of service was attempted.

Compatibility risk is concentrated in permission-denied outcomes that used to succeed, previously ignored schema modules becoming active, stale fields disappearing, custom save hooks starting to run and failed mutations beginning to roll back. These changes require explicit release notes and consumer replay. A new GraphQL field or newly discovered schema can also cause naming collisions or client code-generation changes. Internal tests alone cannot guarantee compatibility.

This was a prioritized audit of approximately 113,852 Python lines across 671 library files, not an exhaustive line-by-line review. Tests ran on one local Python/Django/SQLite combination, with inherited installed packages. No downstream application, remote CI history, production configuration or live PostgreSQL/MySQL server was inspected. The audit makes no blanket claim that other paths are secure or correct.

## B. Architecture, documentation and coverage

### Instructions and actual layout

[AGENTS.md](E:/Projects/libraries/rail-django/AGENTS.md:1) was read; no additional applicable nested AGENTS.md was found. The five requested root references—docs/architecture.md, docs/modules.md, docs/security.md, docs/testing.md and docs/configuration.md—do not exist at this revision. The README directs readers to rail_django/docs. The current HTTP API is under rail_django/http/api, not rail_django/api. These discrepancies are documentation maintenance issues, not missing implementations.

The following existing documents supplied intended behavior and were compared with relevant code:

| Requested subject | Existing references inspected |
| --- | --- |
| Architecture | [rail_django/docs/getting-started/architecture.md](E:/Projects/libraries/rail-django/rail_django/docs/getting-started/architecture.md:1); [rail_django/docs/library/index.md](E:/Projects/libraries/rail-django/rail_django/docs/library/index.md:1) |
| Modules and extension points | [rail_django/docs/library/core/schema-builder.md](E:/Projects/libraries/rail-django/rail_django/docs/library/core/schema-builder.md:1); [rail_django/docs/library/core/schema-registry.md](E:/Projects/libraries/rail-django/rail_django/docs/library/core/schema-registry.md:1); library/generators/type-generator.md; library/security/index.md; library/extensions/index.md |
| Security | [rail_django/docs/security/permissions.md](E:/Projects/libraries/rail-django/rail_django/docs/security/permissions.md:1); [rail_django/docs/reference/security.md](E:/Projects/libraries/rail-django/rail_django/docs/reference/security.md:1); [rail_django/docs/extensions/multitenancy.md](E:/Projects/libraries/rail-django/rail_django/docs/extensions/multitenancy.md:1) |
| Testing | [rail_django/docs/guides/testing.md](E:/Projects/libraries/rail-django/rail_django/docs/guides/testing.md:1); testing harness and pytest configuration |
| Configuration | [rail_django/docs/reference/configuration.md](E:/Projects/libraries/rail-django/rail_django/docs/reference/configuration.md:1); [rail_django/docs/core/configuration.md](E:/Projects/libraries/rail-django/rail_django/docs/core/configuration.md:1) |
| Support/deployment | [rail_django/docs/getting-started/installation.md](E:/Projects/libraries/rail-django/rail_django/docs/getting-started/installation.md:1); deployment guidance, README, CONTRIBUTING and templates |

Large reference documents were read selectively around the settings and contracts traced below. Documentation was treated as intended behavior, not proof of enforcement. Material contradictions include module discovery (RD-008), tenant isolation claims (RD-004), subscription integration (RD-010) and version/support instructions (RD-012). The AGENTS formatting command refers to a nonexistent test file and is absent from the current CI workflow.

### Support: declared, configured in CI and actually verified

| Surface | Declared or documented | CI configuration at this revision | Verified in this audit |
| --- | --- | --- | --- |
| Python | pyproject requires >=3.11; classifiers list 3.11 and 3.12 | Ubuntu matrix 3.11 and 3.12 | Windows Python 3.11.0 only |
| Django | Dependency >=5.0; classifiers 5.0, 5.1, 5.2; install guide says >=4.2 | 5.0.* and 5.2.* for each Python version | 5.2.13 only |
| GraphQL | graphene-django>=3.1.5, graphql-relay>=3.2.0; no direct package constraint on graphene or graphql-core; template adds graphene>=3.4.1 | Resolved transitively, no GraphQL version matrix | graphene 3.4.3, graphene-django 3.2.3, graphql-core 3.2.3, graphql-relay 3.2.0 |
| Database | PostgreSQL recommended; MySQL mentioned; SQLite for development/tests; no explicit server-version matrix found | Framework SQLite settings; no database service matrix | SQLite 3.38.4; PostgreSQL driver installed but no server used |
| Subscriptions | Optional channels>=4.0.0, daphne>=4.0.0 | Installs subscriptions extra | channels 4.3.2, daphne 4.2.1; mocked channel-layer reproduction, no live transport |
| Packaging | setuptools-scm dynamic version; fallback 0.1.7; rail-admin entry point | Separate package-build workflow | No clean build/install performed |

Sources: [pyproject.toml](E:/Projects/libraries/rail-django/pyproject.toml:1), [.github/workflows/ci.yml](E:/Projects/libraries/rail-django/.github/workflows/ci.yml:1), [rail_django/scaffolding/project_template/requirements/base.txt-tpl](E:/Projects/libraries/rail-django/rail_django/scaffolding/project_template/requirements/base.txt-tpl:1), [pytest.ini](E:/Projects/libraries/rail-django/pytest.ini:1). A configured CI matrix is not evidence that those jobs passed for this SHA. Remote run results were not retrieved.

There is no single dependency declaration in practice: requirements.txt delegates to the scaffold base requirements, while pyproject has its own package list. For example, the package allows django-filter>=23.2 and psycopg2>=2.9.9; the template uses django-filter>=24.2 and psycopg2==2.9.9 and includes additional application integrations. The advertised dev/templating/all extras are not defined in pyproject; subscriptions is defined. Resolve these support statements without forcing every application integration into the library runtime dependencies.

The tag at the audited HEAD is v0.1.43. Other tags, including v1.1.6, exist; their ordering does not establish a release lineage for this branch. Installed editable metadata reported 0.1.42.dev1. Source revision, installed metadata and published artifact identity are therefore separate facts.

### Component map and inspection depth

| Area | Responsibility and interaction | Inspection depth |
| --- | --- | --- |
| core (58 Python files) | Configuration/proxy/default merging, GraphQLMeta, registry, schema builders, middleware and scalars | Deep on registry/discovery, builders, settings flow and middleware; sampled scalar conversions and metadata variants |
| generators (89) | Model introspection, Graphene types/inputs, queries/filter pipeline, CRUD/bulk/nested writes, mutation pipelines, subscriptions | Deep on shared list/filter/nested/pipeline paths; sampled aggregation, property ordering, enums, scalar/null/default mapping |
| security (59) | RBAC/ABAC, field and object permissions, operation guards, validation/sanitization | Traced enforcement used by generators and middleware; policy permutations and custom backends not exhaustive |
| extensions (284) | Authentication, tenancy, caching/optimization, audit/events, health, export/import, reports, metadata, forms/tables, tasks, subscriptions | Deep on cache/tenancy/subscriptions; targeted review of export access and row limits, protected media, JWT, event bus and import commit; other internals sampled |
| graphql / http / middleware / views | HTTP routing, multi-schema GraphQL, auth/CSRF, API control endpoints, JWT/request middleware and compatibility imports | Deep on active request/auth/CSRF and schema-management routes; other HTTP handlers sampled |
| management / scaffolding / config | CLI, Django commands, generated project/app settings/requirements, ASGI startup | Template dependency/auth/ASGI/startup review and command inventory; no generated project booted end-to-end |
| testing / tests / examples | Schema harness, synthetic model fixtures, unit/integration/cross-cutting regression suites | Harness read; selected tests inspected; all existing pytest and Django tests executed locally |
| plugins / validation / webhooks / utils / debugging / introspection / migrations | Service interfaces, validation helpers, outbound events, errors, inspection and persistent models | Public/export/dynamic-call searches and targeted security paths; historical migrations and every plugin implementation not exhaustively reviewed |

There are 193 test files. The entire library was inventoried with rg; file/line counts are scope indicators, not a claim that every line was read. Existing tests for JWT token type, transaction exceptions, non-nullable nested relations, tenant filtering and export ownership are useful evidence for those exact cases. They do not prove equivalent enforcement for alternative entry points.

### Execution paths

**Startup and schema construction.** Django invokes [AppConfig.ready](E:/Projects/libraries/rail-django/rail_django/apps.py:16), which can discover schemas, prebuild configured schemas, register templates and metadata-version hooks. Registry discovery tries app modules in schemas → graphql_schema → schema → graphql.schema order, invokes hooks, reads configured schema definitions, then database entries. The registry stores SchemaInfo, builders and compiled instances separately. SchemaBuilder composes query, registration and extension mixins, discovers selected models, initializes generators and builds a Graphene schema. Rebuilds use existing locking/version machinery and update snapshots. RD-007–RD-009 show defects at the boundaries between these layers, rather than a need for a new registry abstraction.

**HTTP GraphQL request.** URL routing reaches [MultiSchemaGraphQLView](E:/Projects/libraries/rail-django/rail_django/graphql/views/multi_schema/view.py:1). Dispatch performs request/CSRF/schema checks and prepares the Graphene view and schema-specific middleware. Django authentication middleware may already supply request.user; header-token verification and the GraphQL authentication layer can also establish or retain identity. GraphQL middleware supplies access guards, field permissions, validation, configured resource controls, audit and performance behavior. Runtime nesting order must be tested through the actual middleware manager, not inferred from the order of a Python list.

A generated list checks model access and operation guards, applies tenant scope and an optional custom resolver, optimizes the queryset, applies filtering/presets/saved filters, ordering and pagination, evaluates the database result and applies output permissions/masking. Single-object and paginated variants share some helpers but have distinct control flow. RD-001 wraps this security-bearing resolver; RD-003 bypasses part of it on error. Nested output fields have their own resolution/permission behavior, which cannot compensate for a skipped root authorization check.

**Mutation.** Input types come from model metadata and field/relation mapping. The pipeline normally performs authentication, model permissions, lookup, guards/ABAC, normalization/sanitization/validation and tenant handling before execution; exact steps vary by operation and can be extended. CRUD factories wrap execution in transaction.atomic. The nested handler implements connect/disconnect/set/create/update/delete; bulk wrappers and custom pipelines are additional entry points. Database writes, model hooks and audit/event side effects precede response construction according to these steps. RD-002 concerns the shared nested detach path; RD-011 concerns the transaction boundary handling returned errors versus raised exceptions. External effects require explicit commit semantics; database rollback does not unsend an external message.

**Configuration to schema/runtime.** Settings dataclasses merge library/environment defaults, global/per-schema Django configuration and registered schema settings; the hierarchical proxy also supports runtime overrides. Model GraphQLMeta and registered app metadata control field exposure, filters, ordering, permissions, operation guards and generated inputs. Builders materialize schema shape, while middleware/resolvers use runtime settings and service factories. Changing settings does not automatically invalidate every compiled object. Two schemas, retained builder references and changes to model selection therefore need explicit compatibility tests.

**Extensions.** Exports use their own access checks, queryset construction, row limits and download-job ownership. Import commit uses a separate atomic service and model manager rather than the CRUD mutation pipeline; its tenant propagation needs follow-up (H-01). Health and management expose operational behavior under configured access controls. The event bus has a bounded queue and redaction/drop handling. Subscription consumer/generator contracts differ from HTTP execution and need transport-level tests, not just generator unit tests.

### Public and extension-facing contract inventory

This is a prioritized inventory, not a complete exported-symbol manifest.

| Contract family | Current examples and expectations to preserve | Compatibility evidence needed |
| --- | --- | --- |
| Root imports and lazy exports | [rail_django/__init__.py](E:/Projects/libraries/rail-django/rail_django/__init__.py:87) returns the SchemaBuilder **class** from get_schema_builder(); [rail_django/core/schema/__init__.py](E:/Projects/libraries/rail-django/rail_django/core/schema/__init__.py:64) takes schema_name and returns a builder **instance**. Similar root generator getters differ from factories under generators. | Import/signature/return-type assertions; do not merge similarly named helpers blindly |
| Registry and extension lifetime | register_schema, register_mutation, get_schema/get_schema_instance/get_schema_builder, discovery hooks, SchemaInfo and custom schema classes; core service factories | Retained references, custom mutation/hook survival, duplicate registration, signal cleanup and worker lifecycle tests |
| Metadata and configuration | GraphQLMeta, app metadata discovery, schema model include/exclude lists, operation guards; RAIL_DJANGO_GRAPHQL and RAIL_DJANGO_GRAPHQL_SCHEMAS; proxy/runtime overrides | Settings precedence snapshots for two schemas, omitted/empty values and runtime reset; metadata-to-introspection comparisons |
| Generated GraphQL | auto_camelcase defaults true; model/type/field naming, list/page variants, ID/scalar/enum mapping, nullable/default values and input relation operations | Introspection snapshots and stored operation replay; generated client compilation; omitted versus explicit null inputs |
| Query semantics | where/basic filters, presets/saved filters, ordering/property ordering, pagination/count modes, custom list resolvers | Ordered result and error assertions, invalid IDs, empty inputs, page caps and counts on representative databases |
| Mutation hooks and pipelines | MutationStep, MutationContext.add_error/add_errors, PipelineBuilder.add_step, response builders, nested handlers, custom validation and save hooks | Atomicity and on_commit assertions; error and success payloads; call counts/order for extension hooks |
| Security | Model permissions, field/object policies, RBAC/ABAC, authentication precedence, tenant context, CSRF and custom guards | Role/user/tenant matrices through both real HTTP and direct GraphQL clients; revoked permission checks |
| HTTP and errors | GraphQL data/errors; CRUD ok/object/errors with field/message/code/severity/details; API timestamp/status/data envelopes; 401/403 behavior | Exact status/body assertions; no raw database detail leakage; authenticated/anonymous/malformed requests |
| Scalars/decorators/services | DateTime/Date/Time/JSON/UUID and custom scalar registry; optimize_query; pluggable optimizer/rate-limiter/audit/cache backends | Custom imports, decorator signatures, serialization round trips and backend lifecycle tests |
| CLI/templates/compatibility paths | rail-admin entry point; Django management commands; project/app templates and ASGI routes; saved_filter compatibility module and views re-exports | Wheel-installed scaffold smoke test, import checks and command argument/help snapshots |

The type generator retains legacy argument handling in input-type creation; that behavior must not be removed incidentally. Duplicate-looking modules adjacent to packages may serve compatibility imports or dynamic loading. Deletion is not recommended without downstream evidence.

## C. Baseline and safe verification

### Isolation and exact command pattern

The initial command was `git status --short`; it produced no entries. `git rev-parse HEAD`, `git log -1 --format=%H%n%aI%n%s` and `git describe --tags --always` recorded the baseline above.

Tests ran from a Git archive in:

`C:\Users\khale\AppData\Local\Temp\rail-django-audit-1d66c29959fe434ca36507d6fc5f3ae4`

A new virtual environment used --system-site-packages so existing packages could be read without installing or changing them. This isolates the executable/configuration and repository writes, **not dependency resolution**. The snapshot source was first on PYTHONPATH; PYTHONDONTWRITEBYTECODE prevented bytecode writes into source packages. Test settings used SQLite and local-memory cache. Logs, temporary synthetic data and pytest artifacts stayed under the temporary directory.

Equivalent PowerShell setup used in the audit:

```powershell
$auditRoot = Join-Path $env:TEMP ('rail-django-audit-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $auditRoot
git archive --format=zip --output="$auditRoot\baseline.zip" HEAD
Expand-Archive -LiteralPath "$auditRoot\baseline.zip" -DestinationPath "$auditRoot\repo"
python -m venv --system-site-packages "$auditRoot\venv"
# Create guard/sitecustomize.py from Appendix 2 before executing tests.
$env:PYTHONPATH = "$auditRoot\guard;$auditRoot\repo"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:DJANGO_SETTINGS_MODULE = 'rail_django.config.test_settings'
Set-Location "$auditRoot\repo"
& "$auditRoot\venv\Scripts\python.exe" -m pytest -m unit --tb=short -q
& "$auditRoot\venv\Scripts\python.exe" -m pytest -m integration --tb=short -q
& "$auditRoot\venv\Scripts\python.exe" -m pytest --tb=short -q
$env:DJANGO_SETTINGS_MODULE = 'rail_django.config.framework_settings'
& "$auditRoot\venv\Scripts\python.exe" -m django test tests.unit --verbosity 1
& "$auditRoot\venv\Scripts\python.exe" -m black --check rail_django/testing tests/unit/test_phase0_regressions.py
& "$auditRoot\venv\Scripts\python.exe" -m black --check rail_django/testing
$env:DJANGO_SETTINGS_MODULE = 'rail_django.config.test_settings'
# Save Appendix 1 as audit_checks.py in the snapshot only.
& "$auditRoot\venv\Scripts\python.exe" -m pytest audit_checks.py -q -s --tb=short
```

Environment assignments were local to each command process; repeated runs supplied the same environment. The guard disables outbound Python socket connections and permits only the internal stdlib socketpair setup needed by Windows asyncio. It is a verification safeguard, not an operating-system network sandbox. Native subprocess networking is not intercepted. Relevant backup/webhook tests were inspected for mocks before execution. No production service or application database was used. Some runs overlapped, so durations are observations, not comparable performance scores.

### Actual versions

Windows 10 build 26200, AMD64; Python 3.11.0; SQLite 3.38.4; Django 5.2.13; graphene 3.4.3; graphene-django 3.2.3; graphql-core 3.2.3; graphql-relay 3.2.0; django-filter 25.2; PyJWT 2.10.1; pytest 9.0.2; pytest-django 4.11.1; channels 4.3.2; daphne 4.2.1; psycopg2 2.9.9; Black 26.1.0; WeasyPrint 68.0. The build module was available, but setuptools_scm was not installed in the inherited environment. No clean build dependency installation was attempted.

### Results

| Check | Outcome | Time / interpretation |
| --- | --- | --- |
| pytest -m unit --tb=short -q | 864 passed, 2 skipped, 618 deselected | 37.13 s |
| pytest -m integration --tb=short -q | 219 passed, 1,265 deselected | 167.24 s |
| Full pytest --tb=short -q | 1,474 passed, 10 skipped, 2 warnings, 3 subtests passed | 514.53 s; includes tests outside either marker |
| Django runner tests.unit --verbosity 1 | 417 run, 4 skipped, OK | 8.459 s; system checks passed |
| Targeted audit_checks.py | 12 passed: 11 defect demonstrations and one query-count benchmark | 2.46 s; tests assert current behavior, not corrected behavior |
| AGENTS Black command | Blocked, exit 2: tests/unit/test_phase0_regressions.py does not exist | This is stale guidance, not a formatter failure in that missing file |
| Black on existing rail_django/testing | Failed, exit 1: harness.py would be reformatted; __init__.py unchanged | No formatting changes made |
| CI Python/Django matrix | Not executed here; workflow inspected | Remote results unknown |
| Clean wheel/sdist and generated-project smoke test | Not run | Missing isolated build prerequisites; inherited environment is insufficient evidence |
| PostgreSQL/MySQL, live Channels/broker, concurrency/load | Not run | No isolated services provisioned |
| Exhaustive dependency advisory scan | Not run | One relevant Django advisory verified; no all-dependency safety claim |

The two full-suite warnings concern tests overriding DATABASES; the backup subprocess was mocked. Error traces deliberately logged by tenant-rejection tests in the Django run were not test failures. Existing skip counts are reported above; the runs did not request the full per-node skip summary, so no invented skip-reason allocation is provided. Source inspection found conditional skips around unsupported business methods, filtering test setup, changed introspection/mutation structure and unavailable user-settings models. Exact skipped node IDs/reasons should be captured with -rs in the next baseline run.

Final preservation check: `git diff --exit-code` passed with no tracked-file changes. `git status --short --untracked-files=all` listed only docs/audits/rail-django-audit.md and docs/audits/rail-django-improvement-plan.md. Both target filenames were absent before creation. All local Markdown file targets and referenced line bounds were checked; key finding locations were also checked against their symbols and execution branches. No source, configuration, dependency declaration or consuming application was changed.

Earlier temporary repro attempts exposed harness problems: a synthetic user's operation was denied by unrelated ABAC defaults, the socket guard initially blocked Windows' internal event-loop socketpair, and the benchmark initially selected a nonexistent Product.tags relation. Only temporary verification code was corrected. These are not reported as library defects. The final reproductions used the actual Post.tags relationship and explicit supported ABAC settings.

### Measured query-count baseline

Workload: 100 synthetic Posts, 10 Categories and 3 Tags; each Post has one category and one tag. A generated list returns 50 rows, selecting title, category.name and tags.name. Settings: default page size 50, maximum 100; model permissions disabled for this benchmark; superuser context; no HTTP middleware. Operation:

```graphql
{ products(limit: 50) { title category { name } tags { name } } }
```

The root field was named products by the temporary test even though the model was Post. Dataset setup and schema construction were excluded from timing. All six executions made **two SQL queries**, consistent with FK select_related plus M2M prefetch. First execution: 9.005 ms. Five subsequent executions: 5.871, 6.116, 5.677, 6.325 and 6.025 ms; median 6.025 ms.

The database/data were already warm; “first execution” is not a cold-process or cold-database measurement. This small SQLite workload, with other checks running, does not support latency percentiles, throughput estimates or production capacity conclusions. It demonstrates that this ordinary nested-list case avoids a per-row relation-query pattern. It does not demonstrate an N+1 defect or a need for a new cache.

Unmeasured paths worth profiling after correctness fixes: per-child authorization/save work, property ordering/filtering materialization (cap 2,000), exact/estimated counts, exports/import row materialization, schema rebuild/reflection and repeated middleware permission checks. Default query page size is 20 and maximum 100; grouping cap is 200. These existing limits should be preserved and tested before proposing new controls. No speedup percentage is claimed.

## D. Prioritized findings

Severity reflects impact and reachability at the library boundary, not a claim about a particular deployed application. “Confirmed” means the described implementation behavior is established by the cited reproduction or static trace. Hypotheses are separated in section F.

| ID | Severity | Category | Finding |
| --- | --- | --- | --- |
| [RD-001](#rd-001) | high | Security / correctness | Opt-in resolver caching can return the wrong result and bypass resolver authorization |
| [RD-002](#rd-002) | high | Security / mutation integrity | Reverse-relation set removes child links without child authorization |
| [RD-003](#rd-003) | high | Security / correctness | Unpaginated query retry discards filters and custom queryset restrictions |
| [RD-004](#rd-004) | high | Security / documented trust boundary | Tenant selection accepts a client header without proving tenant membership |
| [RD-005](#rd-005) | medium | Security / HTTP authentication | An unverified bearer header suppresses session CSRF checks |
| [RD-006](#rd-006) | medium | Security / object access | Numeric saved-filter IDs bypass owner and model checks |
| [RD-007](#rd-007) | medium | Correctness / configuration lifecycle | Re-registering a schema leaves the old compiled schema in service |
| [RD-008](#rd-008) | medium | Correctness / startup | Automatic schema discovery does not import ordinary schema modules |
| [RD-009](#rd-009) | medium | Reliability / startup | Database-backed discovery misses lazy database failures |
| [RD-010](#rd-010) | medium | Correctness / async integration | Generated WebSocket subscriptions register no channel groups |
| [RD-011](#rd-011) | medium | Correctness / transaction contract | A pipeline abort response does not roll back earlier writes |
| [RD-012](#rd-012) | medium | Security / support policy | The tested dependency environment includes a known affected Django release |
| [RD-013](#rd-013) | medium | Reliability / release process | Release publication is not gated on test success for the released commit |

<a id="rd-001"></a>

### RD-001: Opt-in resolver caching can return the wrong result and bypass resolver authorization

**Category:** Security / correctness. **Severity:** high. **Confidence:** confirmed.

**Severity rationale.** High because a reachable configured cache can disclose an authorized caller's result to another caller and skip permission revocation; opt-in activation limits prevalence.

**Verified locations.** [optimize_query.wrapper, lines 108–112](E:/Projects/libraries/rail-django/rail_django/extensions/optimization/decorators.py:108); [_build_query_cache_key, lines 41–72](E:/Projects/libraries/rail-django/rail_django/extensions/optimization/cache.py:41); [generated list resolver](E:/Projects/libraries/rail-django/rail_django/generators/queries/list.py:190).

**Current and expected behavior.** The decorator returns a cache hit before calling the resolver. Generated list resolvers perform model permissions and operation guards inside that resolver. The cache key uses str(info.operation), which is an AST location description, omits resolved field arguments and tenant identity, and includes user identity only when requested. Expected behavior is an authorized result for the exact field invocation.

**Root cause and affected callers.** Caching surrounds the security-bearing resolver and uses an incomplete request identity. Both aliased calls within one operation and separate equal-length operations can share a key. The same defect affects any custom resolver decorated with optimize_query and generated materialized list results. QuerySet results are deliberately not stored; the ordinary generated list path returns a list and is stored.

**Trigger, access and impact.** An application must enable query caching and register a cache backend. An attacker able to invoke the cached field can receive a prior caller's resolver result when keys coincide. A model permission or custom row restriction inside the resolver is skipped. Outer middleware and output field checks may still deny or mask particular fields; they do not make the skipped resolver authorization safe. Default caching is off.

**Evidence.** Temporary test test_cache_collisions_and_permission_bypass used a real Graphene schema, the real decorator and InMemoryQueryCacheBackend, with a stub optimizer/monitor. For { a: secret(value:"A") b: secret(value:"B") }, both aliases returned A and the resolver ran once. Replaying as a user whose resolver would raise denied returned both values with no error. Separate { secret(value:"A") } and { secret(value:"B") } also returned A; str(operation) was OperationDefinitionNode at 0:21.

**Smallest complete correction.** First prevent cache hits from bypassing authorization on generated protected resolvers. Do not present a key-only patch as sufficient. Preserve the decorator signature but temporarily bypass unsafe cross-request result caching where pre-cache authorization cannot be proven. For retained caching, identify the operation and fragments with print_ast, include coerced resolver arguments, parent identity where relevant, schema version, user and trusted tenant context; recheck permissions on every request. Use existing version invalidation and a bounded backend. Do not cache mutable model instances across users.

**Compatibility.** Security correction requiring a documented behavior change. Cache-dependent latency and resolver invocation counts change; incorrect alias results and unauthorized successes disappear. User-specific keys alone do not handle permission revocation or a user switching tenants.

**Required tests and documentation.** Add real decorated GraphQL executions for aliases, equal-length documents, fragment variants, literals/variables, parent-specific results, permission revocation, two users, two tenants and two schemas. Assert permission checks run on hits, writes invalidate results, TTL/eviction limits memory, and cached and uncached responses match. Update caching documentation and release notes.

**Benefit and measurement.** Prevents data disclosure and wrong responses. Measure hit/miss latency, permission-check counts and bounded memory only after semantic equivalence passes. No speedup is claimed.

**Effort and dependencies.** 2–4 engineer-days including compatibility tests; depends on agreeing which existing cached resolvers are explicitly public.

**Remaining uncertainty.** Production cache configuration and downstream decorators were not inspected. Cross-worker invalidation and cache backend behavior remain untested.

<a id="rd-002"></a>

### RD-002: Reverse-relation set removes child links without child authorization

**Category:** Security / mutation integrity. **Severity:** high. **Confidence:** confirmed.

**Severity rationale.** High because a parent-authorized caller can perform a child update that the equivalent explicit operation denies.

**Verified locations.** [NestedOperationHandlerBase.handle_set, lines 513–576](E:/Projects/libraries/rail-django/rail_django/generators/nested/handler.py:513); specifically [unchecked detach, lines 559–562](E:/Projects/libraries/rail-django/rail_django/generators/nested/handler.py:559); compare [handle_disconnect](E:/Projects/libraries/rail-django/rail_django/generators/nested/handler.py:498) and [RelationOperationProcessor._dispatch](E:/Projects/libraries/rail-django/rail_django/generators/nested/operations.py:79).

**Current and expected behavior.** For nullable reverse foreign keys, set computes removed IDs and issues QuerySet.update(FK=None) without resolving or authorizing those children. Explicit disconnect resolves each child and checks update permission and tenant access. Expected behavior is identical authorization for equivalent child changes.

**Root cause and affected callers.** The set implementation optimized the detach half into a bulk update and skipped _resolve_related_instance, _ensure_operation_access and _save_instance. It also bypasses model validation and save signals on removed children. Shared nested handling reaches pipeline create/update and bulk paths that use the handler.

**Trigger, access and impact.** A caller permitted to update a parent with an exposed reverse relation can detach children they cannot update. The relation must permit set and its child FK must be nullable. This does not apply to the existing non-nullable-FK rejection.

**Evidence.** A generated Category update mutation was called with an authenticated user allowed test_app.change_category but denied child Product changes. disconnect:[child_id] returned ok:false and kept the link. set:[] returned ok:true and cleared Product.category_id. ABAC was explicitly disabled through supported settings so an unrelated default ABAC deny did not mask the defect. Existing unified-mutation tests cover non-nullable set, not this authorization difference.

**Smallest complete correction.** Resolve and authorize every removed child before any detach, using the same update/tenant checks as disconnect. Apply the established validated save path or explicitly preserve equivalent validation/signals. Validate all intended changes inside the existing transaction so one denied child leaves every link unchanged. Keep non-nullable and retained-child behavior.

**Compatibility.** Security correction requiring a documented behavior change. Formerly accepted set operations may now be denied; save hooks may run where bulk update bypassed them. The input schema need not change.

**Required tests and documentation.** Parent-only permission, per-child guard deny, mixed allowed/denied children, cross-tenant children, empty set, retained children, nullable/non-nullable FK, and rollback after later failure. Cover the generated GraphQL operation and direct shared handler, plus bulk entry points. Document the permission and side-effect semantics.

**Benefit and measurement.** Prevents unauthorized child updates and restores consistent relation operations. Record query counts for 1/10/100 removed children; do not remove authorization to recover bulk-update speed.

**Effort and dependencies.** 1–2 days; no dependency on broad refactoring.

**Remaining uncertainty.** Custom child save hooks may increase work or introduce external side effects; inventory representative consumers before release.

<a id="rd-003"></a>

### RD-003: Unpaginated query retry discards filters and custom queryset restrictions

**Category:** Security / correctness. **Severity:** high. **Confidence:** confirmed.

**Severity rationale.** High because an error-recovery path expands the data scope, including application ownership restrictions; the trigger requires a related-query database failure.

**Verified locations.** [generate_list_query.resolver, lines 321–340](E:/Projects/libraries/rail-django/rail_django/generators/queries/list.py:321); compare [paginated retry, lines 280–319](E:/Projects/libraries/rail-django/rail_django/generators/queries/list.py:280) and [custom list resolver](E:/Projects/libraries/rail-django/rail_django/generators/queries/list.py:205).

**Current and expected behavior.** If evaluating an unpaginated optimized queryset raises an OperationalError/ProgrammingError and related loading is present, the fallback starts again from manager.all(), reapplies tenant scope, and returns it. It drops where/basic filters, presets, saved filters, ordering and the custom list resolver. Expected behavior is the same filtered, authorized rows or an error.

**Root cause and affected callers.** Duplicated retry implementations differ. The paginated branch rebuilds much of the pipeline; the unpaginated branch bypasses it. _is_schema_error treats any OperationalError/ProgrammingError as a schema error, so the fallback is broader than missing relation columns.

**Trigger, access and impact.** Pagination must be disabled and an optimized related query must fail. Ordinary authorized users can receive extra rows; if an application enforces ownership in its custom list resolver, rows outside that ownership scope may be exposed. Built-in tenant filtering is reapplied, so this is not evidence that the tenant filter itself is dropped.

**Evidence.** A real generated Product list resolver queried two synthetic rows with where:{name:{eq:"visible"}}. An injected missing-column expression on a queryset with prefetch_related caused OperationalError. The fallback returned visible and hidden. The omitted custom-resolver call is separately verified in the code; a deployed missing migration was not created.

**Smallest complete correction.** Prefer failing with the existing sanitized error when optimization fails. If retry is retained, clear only select_related/prefetch_related on the already scoped queryset and preserve all other query clauses. Verify the retry is valid inside transaction.atomic, especially on PostgreSQL; use a savepoint if needed. Avoid reconstructing a permissive base queryset.

**Compatibility.** Security correction requiring a documented behavior change. Consumers relying on an erroneous successful fallback may now receive an error. Valid successful query results and ordering must remain unchanged.

**Required tests and documentation.** Force related-loading errors with pagination on/off, custom ownership resolver, tenant scope, where/presets/saved filters, ordering and property ordering. Assert no extra rows and no duplicated filter usage side effects. Run transaction tests on PostgreSQL as well as SQLite. Document the migration-error behavior.

**Benefit and measurement.** Prevents scope expansion and misleading successful results. No performance benefit is claimed; measure retry query count and error latency.

**Effort and dependencies.** 0.5–1.5 days; independent security PR.

**Remaining uncertainty.** Reproduction injects the database failure. Production frequency and PostgreSQL retry behavior were not measured.

<a id="rd-004"></a>

### RD-004: Tenant selection accepts a client header without proving tenant membership

**Category:** Security / documented trust boundary. **Severity:** high. **Confidence:** confirmed.

**Severity rationale.** High in deployments relying on the documented header-only isolation model because an authenticated model-authorized caller can select another tenant; external validation can mitigate it.

**Verified locations.** [resolve_tenant_id, lines 102–113](E:/Projects/libraries/rail-django/rail_django/extensions/multitenancy/resolver.py:102); [apply_tenant_queryset](E:/Projects/libraries/rail-django/rail_django/extensions/multitenancy/applicator.py:119); [default tenant header](E:/Projects/libraries/rail-django/rail_django/extensions/multitenancy/settings.py:67); [How It Works and client examples](E:/Projects/libraries/rail-django/rail_django/docs/extensions/multitenancy.md:46).

**Current and expected behavior.** When trusted request context or a JWT tenant claim is absent, the supplied X-Tenant-ID (or configured header) becomes the tenant scope without a user-membership check. The guide presents this as isolation and shows switching tenants by header, without explaining the required external trust boundary. Row filtering works for the selected ID; it does not authorize that selection.

**Root cause and affected callers.** Tenant identification and tenant authorization are conflated. The library has no demonstrated membership resolver on this path. Model-level view/change permission applies across the model and is not tenant membership. An empty tenant_header currently falls back to X-Tenant-ID through _coerce_str, so an empty-string setting is not a reliable way to turn the fallback off.

**Trigger, access and impact.** Multitenancy enabled, no prevalidated request tenant or signed tenant claim, user has required model permissions, and no external proxy/membership control. That user can select another tenant's readable rows and may use the analogous scoped mutation paths. A trusted proxy that strips client values and validates membership can mitigate this; its presence was not established.

**Evidence.** Reused TestMultiTenancy's ordinary permissioned user and two organizations. Sending org1's header returned Project 1; changing only the header to org2 returned Project 2. No membership record or membership check was involved. This confirms selection behavior, not a breach of a particular consuming application.

**Smallest complete correction.** Make the trust requirement explicit and fail closed when tenant scope is not validated. Prefer existing authenticated request.tenant_id or verified JWT claim. If applications need header selection, require a configured authorization callback or a documented trusted-proxy integration that validates selection before resolution. Permit disabling the header fallback explicitly; do not invent a universal membership model.

**Compatibility.** Security correction requiring a documented behavior change, potentially breaking current header-only clients. A callback is justified only by the concrete need to support application-specific membership. Ship migration instructions and test trusted-context and signed-claim alternatives; do not leave an insecure default enabled for compatibility.

**Required tests and documentation.** Same user/other tenant denial, authorized multi-tenant selection, header/claim precedence, forged headers, absent context, inactive users, superuser policy, and two schemas. Replay query and mutation operations. Correct the guide's blanket 404 assertion: GraphQL results/errors are operation-dependent.

**Benefit and measurement.** Establishes actual tenant authorization rather than only filtering by caller-selected identity. Measure membership-check counts with request-scoped reuse; no shared cache without revocation and tenant separation.

**Effort and dependencies.** 2–4 days plus consumer migration; maintainer must define the supported trust contract.

**Remaining uncertainty.** External middleware/proxy controls and consumer membership models are unknown. No consuming application was read or modified.

<a id="rd-005"></a>

### RD-005: An unverified bearer header suppresses session CSRF checks

**Category:** Security / HTTP authentication. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium because the control failure is reproduced, but exploitation requires a browser/request path that can send credentialed custom headers.

**Verified locations.** [is_session_authenticated_request, lines 27–34](E:/Projects/libraries/rail-django/rail_django/utils/csrf.py:27); [BaseAPIView._authenticate_request, especially lines 84–86](E:/Projects/libraries/rail-django/rail_django/http/api/views/base.py:82); [GraphQL dispatch CSRF check](E:/Projects/libraries/rail-django/rail_django/graphql/views/multi_schema/view.py:133) and [get_context](E:/Projects/libraries/rail-django/rail_django/graphql/views/multi_schema/view.py:263).

**Current and expected behavior.** A request with an authenticated session is classified as non-session merely because its Authorization header starts with Bearer or Token. BaseAPIView accepts the existing session before token verification, and GraphQL can retain that identity. Expected behavior is CSRF enforcement for cookie/session identity unless a validated header credential is the identity actually used.

**Root cause and affected callers.** The CSRF helper infers authentication provenance from an attacker-controlled string. There is also an auth_method == jwt exemption that does not, by itself, distinguish header JWT from cookie JWT; cookie-auth middleware must continue enforcing its own CSRF policy.

**Trigger, access and impact.** A victim has an authenticated browser session and an attacker can arrange a credentialed request with that header, for example through an allowed cross-origin frontend under attacker control. Arbitrary unrelated origins cannot normally set Authorization without a successful preflight. This is not an unconditional drive-by CSRF claim.

**Evidence.** RequestFactory POST with an authenticated synthetic user and no CSRF token returned 403 from the helper. Adding Bearer definitely-invalid made BaseAPIView._authenticate_request and the CSRF helper both return None, while the session user remained. No browser attack or remote request was attempted.

**Smallest complete correction.** Track validated authentication provenance. Keep CSRF checks when the session is retained; exempt only successfully validated explicit header-token authentication. Decide and document precedence for session plus invalid header. Reuse the helper in active GraphQL and REST paths and inspect cookie JWT middleware before changing its exemption.

**Compatibility.** Security correction requiring a documented behavior change. Clients sending a dummy/stale bearer header alongside cookies may start receiving 401/403. Valid header-only clients should retain existing behavior and session clients should send CSRF tokens.

**Required tests and documentation.** Django Client(enforce_csrf_checks=True) across GraphQL and REST: session only, invalid/valid bearer plus session, header only, JWT cookie, multipart, allowed/disallowed origins and safe methods. Preserve error status/body contracts. Update authentication guidance.

**Benefit and measurement.** Restores the CSRF boundary for session identity. No throughput improvement is claimed.

**Effort and dependencies.** 1–2 days; coordinate with authentication owners.

**Remaining uncertainty.** Cross-origin exploitability depends on deployed CORS, cookies, proxy and frontend trust. Those settings were not audited.

<a id="rd-006"></a>

### RD-006: Numeric saved-filter IDs bypass owner and model checks

**Category:** Security / object access. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium because private saved-filter use and metadata are exposed to model-authorized callers; underlying model access is not bypassed by this finding.

**Verified locations.** [QueryFilterPipeline._load_saved_filter, lines 174–201](E:/Projects/libraries/rail-django/rail_django/generators/queries/base.py:174); [usage-stat update](E:/Projects/libraries/rail-django/rail_django/generators/queries/base.py:212); [existing saved-filter coverage](E:/Projects/libraries/rail-django/tests/integration/test_saved_filters.py:1).

**Current and expected behavior.** Lookup by name restricts model_name and requires a shared filter or its creator. Numeric ID lookup returns the first matching row before either restriction. Expected behavior is the same access rule for both identifiers.

**Root cause and affected callers.** Two lookup branches build different querysets. Both list and paginated query builders use QueryFilterPipeline. The backward-compatible rail_django.saved_filter import delegates to the same extension model.

**Trigger, access and impact.** A caller allowed to query a model can submit another user's private filter ID and observe its effect and update its usage counters. Cross-model IDs are also accepted. This does not bypass the underlying model queryset's tenant or model permission checks.

**Evidence.** Created a private Product filter owned by one synthetic user. A different user got None by its name but received the SavedFilter instance by its numeric primary key. Existing integration tests test private-name denial and shared-ID success, missing private-ID denial.

**Smallest complete correction.** Build one model-scoped, owner/shared-authorized queryset, then apply ID or name lookup to it. Preserve the current unavailable-filter behavior unless deliberately versioning its error contract. Do not update usage for inaccessible filters.

**Compatibility.** Security correction requiring a documented behavior change. Unauthorized numeric IDs stop applying; authorized IDs and names keep their behavior. No schema change is necessary.

**Required tests and documentation.** Owner/non-owner/anonymous, shared/private, ID/name, another model, nonexistent ID, and usage counters for both list and page. Document visibility semantics.

**Benefit and measurement.** Protects private filter definitions and avoids cross-model misuse. Verify query counts remain bounded; no performance gain is claimed.

**Effort and dependencies.** 0.5–1 day; independent PR using existing model and helper.

**Remaining uncertainty.** The model scopes by model class name, not app label; a wider naming migration requires separate evidence and is not proposed here.

<a id="rd-007"></a>

### RD-007: Re-registering a schema leaves the old compiled schema in service

**Category:** Correctness / configuration lifecycle. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium because acknowledged configuration changes can leave removed fields active and added fields unavailable until rebuild; no deployed disclosure was demonstrated.

**Verified locations.** [SchemaRegistry.register_schema, especially lines 121–129](E:/Projects/libraries/rail-django/rail_django/core/registry/registry.py:73); [get_schema_builder](E:/Projects/libraries/rail-django/rail_django/core/registry/builders.py:13); [get_schema_instance](E:/Projects/libraries/rail-django/rail_django/core/registry/builders.py:78); [SchemaDetailAPIView.put](E:/Projects/libraries/rail-django/rail_django/http/api/views/schema_detail.py:31).

**Current and expected behavior.** Registration replaces SchemaInfo and drops the outer instance/model caches but retains the existing builder and its _schema. Re-registering a different model selection can therefore return the identical compiled schema. The REST update reports success through the same registration method.

**Root cause and affected callers.** There are two cache layers, and only one is invalidated. The existing _dispose_builder helper already disconnects builder signals when removal is intended. Settings-only refresh does not guarantee a model-selection rebuild.

**Trigger, access and impact.** A schema has already been built, then its apps/models/exclude_models are updated under the same name. Newly included fields may be missing and removed fields can remain available until a rebuild/restart. Restriction changes may have security consequences, but this audit reproduced schema staleness rather than a separate authorization exploit.

**Evidence.** A fresh SchemaRegistry registered audit_reregister with Category, obtained a Graphene schema, then re-registered it with Product. get_schema_instance returned the identical object (first is second). All calls used real builders.

**Smallest complete correction.** Invalidate/rebuild the retained builder or dispose it using the existing lifecycle helper when schema-shaping registration changes. Preserve explicitly registered custom mutations and extension hooks according to a documented lifetime contract; blindly replacing the builder may lose them. Invalidate associated middleware/introspection caches as needed and clear removed runtime settings.

**Compatibility.** Observable bug fix that may affect existing callers. Updated schema definitions finally take effect; previously stale fields disappear. Returning a new builder can affect callers that retain builder references.

**Required tests and documentation.** Register/build/update/rebuild with changed model selection, exclusions, empty settings, duplicate registration, disabled schemas, preserved custom mutations/hooks, version increments and signal cleanup. Snapshot before/after introspection and replay operations. Cover REST PUT and programmatic registration, then concurrent build/update.

**Benefit and measurement.** Makes configuration changes reliable and reduces reliance on worker restarts. Measure build count per registration and retained signal handlers; no latency gain promised.

**Effort and dependencies.** 1–3 days; requires agreement on builder extension lifetime.

**Remaining uncertainty.** Concurrent requests and multi-process invalidation were not tested. Updating one process is not evidence that every worker reloads.

<a id="rd-008"></a>

### RD-008: Automatic schema discovery does not import ordinary schema modules

**Category:** Correctness / startup. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium because ordinary documented app layouts silently fail discovery and behavior depends on incidental imports.

**Verified locations.** [_discover_app_schemas, lines 51–69](E:/Projects/libraries/rail-django/rail_django/core/registry/discovery.py:51); [discover_schemas](E:/Projects/libraries/rail-django/rail_django/core/registry/discovery.py:18) and [auto_discover_schemas](E:/Projects/libraries/rail-django/rail_django/core/registry/discovery.py:40).

**Current and expected behavior.** The discovery loop calls Django import_string on module paths such as app.schema. That imports the parent and reads a schema attribute; it does not reliably import the submodule. A normal app with an empty __init__.py and schema.py is skipped until another import exposes it.

**Root cause and affected callers.** A dotted-symbol loader is used where a module loader is needed. ImportError and AttributeError are silently treated as absent modules, including some genuine import failures. This affects startup discovery, registry helpers, discovery management/API callers and generated app conventions.

**Trigger, access and impact.** An installed app defines SCHEMA_CONFIG or register_schema in one of the advertised discovery modules but has not already imported that module. Import order can change the visible schemas.

**Evidence.** A temporary audit_app package had an empty __init__.py and schema.py containing SCHEMA_CONFIG. _discover_app_schemas registered nothing. After importlib.import_module('audit_app.schema'), the same call registered the schema.

**Smallest complete correction.** Use importlib.import_module for candidates. Ignore only a genuinely absent candidate module; report dependency/import failures inside an existing module with context. Preserve documented candidate order and registration hooks.

**Compatibility.** Observable bug fix that may affect existing callers. Previously ignored schemas/hooks may now load, and previously hidden errors become visible. Discovery can add GraphQL fields or create naming collisions, so the change is not automatically harmless.

**Required tests and documentation.** Each candidate layout, empty package initializer, missing candidate, failing dependency, SCHEMA_CONFIG and registration callback, duplicate names and repeat discovery. Add a scaffold startup smoke test and document precedence.

**Benefit and measurement.** Deterministic discovery independent of incidental imports. Measure discovered names and startup build count, not speculative speedups.

**Effort and dependencies.** 0.5–1 day; independent from RD-009.

**Remaining uncertainty.** No downstream app discovery modules were inspected; collisions must be assessed with representative consumers.

<a id="rd-009"></a>

### RD-009: Database-backed discovery misses lazy database failures

**Category:** Reliability / startup. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium because fresh or recovering databases can interrupt startup/discovery; startup callers sometimes catch the failure.

**Verified locations.** [_register_schemas_from_database, lines 87–110](E:/Projects/libraries/rail-django/rail_django/core/registry/discovery.py:87); [optional startup discovery](E:/Projects/libraries/rail-django/rail_django/apps.py:41) and [get_schema_builder discovery](E:/Projects/libraries/rail-django/rail_django/core/schema/__init__.py:73).

**Current and expected behavior.** The OperationalError/ProgrammingError handler wraps objects.all(), which is lazy. Iterating entries happens outside the handler, where database access actually occurs. Missing registry tables or unavailable databases therefore escape the intended graceful skip.

**Root cause and affected callers.** The exception boundary does not cover queryset evaluation. The per-entry try block also starts after iteration has already obtained the next row. Startup catches some resulting exceptions broadly; direct discovery/get_schema callers can still fail and initialized state remains incomplete.

**Trigger, access and impact.** Fresh database before migrations, temporarily unavailable database, or missing SchemaRegistryModel table when discovery runs. No production database was contacted.

**Evidence.** A synthetic lazy iterable returned by the actual discovery helper's model manager raised OperationalError on __iter__. The error escaped _register_schemas_from_database. This precisely exercises the intended handler boundary; it is not an availability test against a real database server.

**Smallest complete correction.** Put database iteration inside the specific exception boundary, preserving successful settings/app registration. Do not swallow arbitrary coding errors. Define when database entries will be retried after recovery or migrations so a temporary failure does not permanently mark discovery complete.

**Compatibility.** Observable bug fix. Previously failing discovery can now serve settings-defined schemas; applications must not silently serve an unintended fallback when database schema definitions are security-critical.

**Required tests and documentation.** Real empty temporary database/missing table, lazy query failure, successful rows, malformed row handling, recovery/retry and startup management commands. Document the difference between optional database discovery and required configuration.

**Benefit and measurement.** Predictable startup and useful diagnostics. Measure startup attempts and avoid repeated failing DB queries per request.

**Effort and dependencies.** 0.5–1 day; can follow RD-008 in a separate small PR.

**Remaining uncertainty.** Maintainer must specify whether database registration is optional in each supported deployment mode.

<a id="rd-010"></a>

### RD-010: Generated WebSocket subscriptions register no channel groups

**Category:** Correctness / async integration. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium because the advertised optional transport silently accepts subscriptions that never receive events; no working transport data leak was demonstrated.

**Verified locations.** [RailGraphqlWsConsumer.handle_subscribe, lines 84–133](E:/Projects/libraries/rail-django/rail_django/extensions/subscriptions/consumer.py:84); [generated resolver, lines 234–248](E:/Projects/libraries/rail-django/rail_django/generators/subscriptions/generator.py:234); [get_subscription_consumer](E:/Projects/libraries/rail-django/rail_django/extensions/subscriptions/consumer.py:209); [scaffold WebSocket routes](E:/Projects/libraries/rail-django/rail_django/scaffolding/project_template/root/asgi.py-tpl:30).

**Current and expected behavior.** The consumer passes a dict with is_subscription/is_publication keys. Generated resolvers read those flags with getattr, so both appear false and return None. The consumer accepts the null result and records an operation with no groups, producing a silent nonfunctional subscription.

**Root cause and affected callers.** Consumer and generator disagree on context representation. A one-line dict-to-object change is insufficient: the generator returns group-name lists during initialization through a GraphQL field declared as an object type. The factory also ignores its schema_name argument, and the scaffold passes consumer classes directly rather than .as_asgi() callables. These adjacent contracts must be checked together.

**Trigger, access and impact.** An application enables the Channels integration and submits an ordinary generated subscription. Required subscription dependencies were installed in the audit environment.

**Evidence.** A real generated Category subscription and Graphene schema were passed to the actual consumer. handle_subscribe for subscription { categoryCreated { id event } } completed with _subscriptions['1']['groups'] == [] and zero channel_layer.group_add calls. Only the channel layer and outbound send were AsyncMocks. No real socket/server was used.

**Smallest complete correction.** Choose one supported initialization/publication contract and use it consistently. Keep channel-group registration separate from GraphQL output serialization, or adopt the existing GraphQL subscribe/async-iterator API without adding a library. Correct consumer binding and scaffold .as_asgi() usage. Before enabling repaired delivery, enforce authentication, per-event object/field authorization and tenant scope in the live transport.

**Compatibility.** Observable bug fix; repaired subscriptions begin delivering events where they previously did nothing. Any protocol/schema changes beyond graphql-transport-ws and existing field names need a separate compatibility decision.

**Required tests and documentation.** Channels communicator end-to-end: connection init, schema routing, subscribe, committed create/update/delete publication, rollback suppression, filters, authorization revocation, two tenants, disconnect/duplicate operation IDs and cleanup. Snapshot event envelopes and test actual generated ASGI routes.

**Benefit and measurement.** Functional subscription delivery with an explicit security boundary. Measure event latency, active group/task count and cleanup under a bounded local workload after correctness passes.

**Effort and dependencies.** 3–5 days; larger than a context-type patch. Depends on maintainer agreement about supported protocol and tenant behavior.

**Remaining uncertainty.** Live delivery, broker behavior and async ORM boundaries were not verified. Missing tenant/model controls on publication are a follow-up security concern, not a demonstrated event leak while delivery is broken.

<a id="rd-011"></a>

### RD-011: A pipeline abort response does not roll back earlier writes

**Category:** Correctness / transaction contract. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium because supported custom pipeline failures can commit partial state and make retries unsafe; the default exception path already rolls back.

**Verified locations.** [BasePipelineMutation.mutate, lines 121–165](E:/Projects/libraries/rail-django/rail_django/generators/pipeline/factories/base.py:121); [MutationContext.add_error](E:/Projects/libraries/rail-django/rail_django/generators/pipeline/context.py:71); [create response builder](E:/Projects/libraries/rail-django/rail_django/generators/pipeline/factories/create.py:64); [existing exception rollback test](E:/Projects/libraries/rail-django/tests/unit/test_pipeline_transactions.py:1).

**Current and expected behavior.** Exceptions trigger transaction.set_rollback(True), but a returned context with should_abort=True goes directly to build_response inside atomic. A custom step can write, add_error, and return ok:false while the write commits. Expected behavior for a failed atomic mutation is no persisted partial write.

**Root cause and affected callers.** The public pipeline supports failure through context state as well as exceptions; the transaction wrapper handles only one mechanism. PipelineBuilder.add_step and custom/reordered execution steps make this reachable through documented extension points. The current regression covers raised ValidationError only.

**Trigger, access and impact.** A custom step writes before recording an error, or a later step aborts after execution. No claim is made that every default CRUD failure partially commits; the verified case uses the supported custom-step contract.

**Evidence.** A temporary MutationStep created a Category then called ctx.add_error('Synthetic business rule rejected'). A BasePipelineMutation using that pipeline returned ok:false, but the Category still existed after mutate returned.

**Smallest complete correction.** After execute_pipeline, mark the current atomic block for rollback when ctx.should_abort is true before building the response. Do not roll back warning-only contexts. Apply the same rule to any alternate pipeline entry points and keep external side effects deferred with on_commit where commit success matters.

**Compatibility.** Observable bug fix that may affect callers relying on partial writes after an error response. The success/error payload shape can remain unchanged; transaction and on_commit behavior changes.

**Required tests and documentation.** Write-then-add_error, later rejecting step, add_errors, raised exceptions, warnings, nested and outer transactions, delete/update/create, and on_commit suppression. Document that failed mutations are atomic and audit attempts versus successful writes are distinct.

**Benefit and measurement.** Prevents unexpected persisted state and duplicate work after clients retry failed operations. Verify row counts and side-effect calls rather than latency.

**Effort and dependencies.** 0.5–1 day; independently reviewable shared-boundary fix.

**Remaining uncertainty.** Downstream custom pipeline semantics and non-database side effects were not inventoried.

<a id="rd-012"></a>

### RD-012: The tested dependency environment includes a known affected Django release

**Category:** Security / support policy. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium for this framework audit: the installed Django version is in a verified affected range, but the ASGI exposure and upstream limits of deployments are unknown. Django classifies the underlying issue low; the reviewed advisory lists moderate.

**Verified locations.** [Python support](E:/Projects/libraries/rail-django/pyproject.toml:10), [Django classifiers](E:/Projects/libraries/rail-django/pyproject.toml:19) and [Django>=5.0 dependency](E:/Projects/libraries/rail-django/pyproject.toml:30); [CI matrix](E:/Projects/libraries/rail-django/.github/workflows/ci.yml:14); [scaffold dependency floor](E:/Projects/libraries/rail-django/rail_django/scaffolding/project_template/requirements/base.txt-tpl:3).

**Current and expected behavior.** The actual local baseline uses Django 5.2.13. CVE-2026-5766 affects >=5.2,<5.2.14 and >=6.0,<6.0.5. The framework's broad floor also permits obsolete or affected releases. This is verified dependency exposure, not proof that a deployed application is exploitable.

**Root cause and affected callers.** No lock/constraints set establishes a tested resolved runtime, and the declared support/CI matrix still includes Django 5.0. The install guide also says Django>=4.2 while package metadata requires >=5.0. A passing test suite does not detect advisory exposure.

**Trigger, access and impact.** An affected version serves ASGI requests with missing/understated Content-Length and insufficient upstream body limits. An unauthenticated remote client may cause excessive upload memory use before GraphQL authentication. No large upload was sent in this audit.

**Evidence.** Version inventory: Django 5.2.13; scaffold has an ASGI entry point and GraphQL multipart handling. The affected range and fix are confirmed by the [Django advisory](https://www.djangoproject.com/weblog/2026/may/05/security-releases/) and [reviewed range record](https://github.com/advisories/GHSA-w26r-rmm8-9c29). Django's [support table](https://www.djangoproject.com/download/) dates end of extended support to 2025-04-02 for 5.0 and 2025-12-03 for 5.1.

**Smallest complete correction.** Test and document a currently supported patched Django series, update affected deployment constraints in their own authorized work, and reconcile package/scaffold/docs/CI support statements. Preserve compatibility by separating patch-level security upgrades from a decision to drop old major/minor support. Do not merely pin 5.2.14 as a permanent target; later fixes also exist.

**Compatibility.** Security correction requiring a documented dependency behavior change; ending Django 5.0/5.1 support is a breaking support-policy change requiring explicit release treatment. No dependencies were changed by this audit.

**Required tests and documentation.** Resolve clean environments for minimum/current supported versions, run the full suite and consumer operation replay, build/install wheel and sdist, and check bounded ASGI uploads. Run a complete advisory scan on deployment lockfiles, then verify each relevant advisory and exposure.

**Benefit and measurement.** Removes a verified affected dependency from supported deployment guidance. Measure resolved versions and memory/body-limit behavior; no invented speedup.

**Effort and dependencies.** 1–2 days for baseline matrix/advisory work, excluding consumer upgrade remediation; depends on support policy.

**Remaining uncertainty.** No exhaustive transitive CVE scan or deployment dependency inventory was performed. The user's installed packages were not altered.

<a id="rd-013"></a>

### RD-013: Release publication is not gated on test success for the released commit

**Category:** Reliability / release process. **Severity:** medium. **Confidence:** confirmed.

**Severity rationale.** Medium because release automation can publish an untested revision or leave a tag after a failed build; no historical bad release was established.

**Verified locations.** [release triggers](E:/Projects/libraries/rail-django/.github/workflows/tag-release.yml:3); [tag_release job](E:/Projects/libraries/rail-django/.github/workflows/tag-release.yml:14); [tag push before artifact build](E:/Projects/libraries/rail-django/.github/workflows/tag-release.yml:85); [separate tests job](E:/Projects/libraries/rail-django/.github/workflows/ci.yml:8).

**Current and expected behavior.** A push to main/master starts a workflow that tags, builds and publishes release files without waiting for the separate CI workflow. A failing commit or failed artifact build can therefore acquire a release tag. Branch protection may reduce exposure but does not establish this workflow dependency.

**Root cause and affected callers.** Release and validation workflows are independently triggered. There is no needs edge or verified successful workflow completion for the exact commit before tagging. The workflow's contents:write permission makes publication possible.

**Trigger, access and impact.** A push or manual release run when tests have not succeeded for that revision, or a build failure after tag creation. No live release or tag was created during the audit.

**Evidence.** Static execution trace of all three workflow files: the release job installs packaging tools, computes the version, checks remote tag/release existence, pushes a tag, then builds and uploads. It contains no test step and no dependency on CI.

**Smallest complete correction.** Gate release publication on successful tests and package smoke checks for the exact SHA, using a shared workflow/job dependency or a carefully validated completed-CI trigger. Build and verify artifacts before creating the tag. Preserve branch/tag/version conventions and avoid re-running publication for unrelated or untrusted events.

**Compatibility.** Internal change with no intended application-visible difference. Release timing and automation behavior change, so maintainers must validate workflow permissions and duplicate-run behavior.

**Required tests and documentation.** Dry-run event/commit selection, failing tests/build means no tag or release, successful matrix publishes the tested SHA, retry/idempotency, existing-tag behavior and least required token permissions. Add release-process documentation.

**Benefit and measurement.** Prevents publication of unverified artifacts. Measure the invariant that each published SHA has matching successful required checks.

**Effort and dependencies.** 0.5–1.5 days; can proceed before runtime fixes.

**Remaining uncertainty.** Remote branch protections, environments and historical Actions results were not accessible in this audit; no claim that a bad release has actually shipped.

## E. Compatibility assessment and rollout

Classification meanings:

- **Internal:** no intended observable application difference; still validate operational behavior.
- **Additive:** new API/configuration/schema surface requiring compatibility checks.
- **Observable fix:** callers may see different results, failures or side effects.
- **Security correction:** a documented behavior change is necessary to close the boundary.
- **Breaking:** deprecation or explicit major-release/support-policy treatment is needed.

| Finding | Classification and affected contract | Consumer risk | Required validation | Rollout needs |
| --- | --- | --- | --- | --- |
| RD-001 | Security correction; optimize_query/decorator and backend contracts, response identity | Cache hits now authorize; stale/shared results disappear; latency can increase | Cached/uncached replay, arguments/aliases, permission revocation, tenant/schema separation, bounded backend lifecycle | Disable unsafe cache paths before patch rollout; clear/version existing entries; publish cache semantics |
| RD-002 | Security correction; nested set semantics and child save hooks | Formerly accepted detach denied; extra hooks/query work | Generated and bulk mutation replay, child policy/tenant tests, rollback and signal assertions | Release-note permission tightening and hook changes; application hook review |
| RD-003 | Security correction; query fallback/error contract | Database problems produce errors instead of broadened success | Scoped/filter/order response assertions with injected failures on SQLite/PostgreSQL | Prefer safe failure; document migration/repair expectations |
| RD-004 | Security correction; tenant identity/trust contract; authorized-header callback would be additive | Header-only clients need trusted context, verified claims or membership authorization | Same-user/two-tenant HTTP+mutation replay, precedence, absent context, revocation | Explicit migration guide and release decision; coordinate consumer/proxy change before enforcement; unsafe deployments must be contained |
| RD-005 | Security correction; auth precedence and CSRF HTTP statuses | Stale token plus session may receive 401/403 | Real CSRF-enforcing client, cookie/header/session matrix and error envelopes | Publish supported credential precedence; migrate clients to valid tokens or session CSRF tokens |
| RD-006 | Security correction; saved-filter lookup semantics | Private/other-model numeric IDs no longer apply | Owner/shared/model visibility and usage-counter assertions for list/page | No data migration expected; preserve unavailable-filter behavior |
| RD-007 | Observable fix; registration, builder reference and custom-extension lifetime | Removed fields disappear; retained references may become stale; custom mutations could be lost by an incomplete fix | Introspection diffs, operation replay, extension survival, signal cleanup, concurrent update | Choose builder lifetime; rebuild/restart all affected workers coherently; no claim of automatic cross-process propagation |
| RD-008 | Observable fix; discovery module convention and error handling | Previously ignored modules load; collisions/import errors become visible | Scaffold/app layouts, candidate precedence, repeated discovery, consumer startup | Announce discovery correction; inspect discovered names before production rollout |
| RD-009 | Observable fix; optional database configuration/startup | Serving partial configuration could surprise required-registry deployments | Missing table/outage/recovery tests; required-versus-optional policy | Publish startup/failure policy and retry trigger; do not silently fail open |
| RD-010 | Observable fix; subscription transport, event envelope and factory | Events begin arriving; schema/protocol redesign could be breaking | End-to-end authenticated Channels tests, tenant/per-event controls, event snapshots | Keep feature disabled until delivery and authorization gates pass; protocol changes need separate decision |
| RD-011 | Observable fix; failed mutation atomicity and on_commit | Partial writes formerly persisted; callbacks now suppressed on failure | Custom-step, warnings/errors, nested/outer transaction and response tests | Document atomic failure; review retry behavior and external effects |
| RD-012 | Security dependency change; dropping old Django series is breaking support policy | Dependency resolution/installability and framework integration | Clean min/current environments, complete suite, wheel/scaffold install and consumer replay | Separate patch upgrade from support removal; deployment constraints and rollback to another supported patched release |
| RD-013 | Internal application change; release automation behavior | Maintainer release timing/idempotency changes | Exact-SHA gate, failure dry runs, build-before-tag, retry tests | Validate Actions permissions/protections; no application migration |

No blanket compatibility guarantee is supported. Capture public import signatures, introspection and representative operations before each change. Store both successful and denied operations, empty/invalid identifiers, omitted/null values, error bodies and hook side effects. Differences should be either absent or individually approved as the intended finding correction. Additive tenant settings or GraphQL exposure still require this review.

Use small independently reviewable PRs from the plan. Security changes should preserve safe valid results but must not retain unauthorized behavior for compatibility. Avoid a general “legacy insecure mode.” If a coordinated transition cannot occur immediately, disable the affected optional feature or restrict its endpoint while preparing the secure path. Rollback must not re-expose the vulnerable path.

## F. Hypotheses, open questions and assessment limits

The following items are **not confirmed vulnerabilities or measured bottlenecks**. They are specific gaps requiring evidence before an implementation recommendation.

| ID / topic | Supporting observation | Missing evidence / next check |
| --- | --- | --- |
| H-01: import/tenant and row authorization | Import commit is atomic but uses model.objects.filter for matching updates and model.objects.create, outside the generated CRUD pipeline: [commit_batch](E:/Projects/libraries/rail-django/rail_django/extensions/importing/services/commit_service.py:80), [lookup](E:/Projects/libraries/rail-django/rail_django/extensions/importing/services/commit_service.py:114). Batch/template access controls exist upstream. | Trace authenticated upload → simulate → validate → commit with two tenants and cross-tenant matching keys; establish whether descriptors/upstream checks constrain both target rows and FK values. Do not infer an exploit from the manager call alone. |
| H-02: repaired subscription publication authorization | Initialization is broken (RD-010); channel-group registration/publication paths require a different context from HTTP. | Once functional, demonstrate object/field policy and tenant checks at each delivery, including permission revocation and delete events. No event leak has been demonstrated. |
| H-03: production GraphQL resource controls | [QueryComplexityMiddleware](E:/Projects/libraries/rail-django/rail_django/core/middleware/performance.py:93) limits only selected query roots/operation names; selectors default empty. [RuntimeSettings](E:/Projects/libraries/rail-django/rail_django/core/runtime_settings.py:17) has rate limiting off by default. Pagination, property-processing and grouping caps already exist. | Establish intended public-endpoint policy and actual proxy/request limits; bounded tests for aliases/fragments/batching/depth, many root fields, mutation cost and exports. Opt-in selectors are intentional code behavior; do not call the default a bypass without its deployment contract. |
| H-04: retained objects and concurrent schemas | Multiple process-local caches/builders/service registries exist; rebuild locks and disposal helpers also exist. | Long-lived two-schema create/rebuild/unregister workload with handler/object counts and memory, plus concurrent reads/updates. No leak/race measured. |
| H-05: performance beyond ordinary optimized lists | Counts/property processing, export/import materialization and per-row permission work can consume resources; one ordinary list benchmark made two queries. | Representative roles, cardinalities, database indexes and workloads; compare exact responses and policy checks along with CPU/query/memory measurements. No blanket N+1 or caching recommendation. |
| H-06: upload/export/media/outbound trust boundaries | Sampled protected-media handling resolves paths within its configured root and requires authentication; export row/job access guards and signed/redacted event helpers exist. Some formatters, report engines and outbound integrations are pluggable. | End-to-end object ownership for files, symlink/storage behavior, archive/decompression limits, spreadsheet formula handling, URL allowlists/redirects and outbound webhooks on isolated resources. Existing helpers are not proof every caller is protected. |

### Maintainer questions

1. Which Python, Django and database versions are contractual today? pyproject, installation docs, templates and CI disagree. Evidence needed: release policy and clean-environment matrix results, including GraphQL transitive versions.
2. Is database-backed schema registration optional or required when unavailable? Evidence needed: expected fresh-install/migrate/recovery behavior and whether serving settings-only schemas is safe.
3. May a schema update replace a retained builder, or must custom mutations/hooks survive on the same builder? Evidence needed: extension documentation and representative consumer usage.
4. What validates tenant membership in supported deployments? Evidence needed: authenticated request/JWT/proxy integration and consumer membership rules. No consuming app was inspected.
5. Which resolvers currently enable caching, and which results are explicitly public? Evidence needed: application configuration, backend/invalidation choices and revocation requirements.
6. Which subscription protocol and event envelope are supported? Evidence needed: real client operations, ASGI routes, broker setup and authorization expectations.
7. Are failed custom pipeline mutations always intended to be atomic? Evidence needed: documented extension contract and consumers using add_error after execution.
8. What remote branch protections and required checks govern releases? Evidence needed: repository settings and Actions run/check results for the exact release SHA.
9. What caused the skipped existing tests? Evidence needed: node-level -rs output and supported-feature decisions; a skipped test is neither a pass nor proof of a defect.
10. What package constraints are deployed? Evidence needed: authorized consumer lockfiles and runtime inventory before extending the one verified advisory into a broader vulnerability assessment.

### What was not established

No all-version or all-database compatibility claim; no production workload benchmark; no operating-system network sandbox; no penetration test against a deployment; no complete transitive dependency audit; no guarantee about custom authorization backends, storage, broker, workers or downstream hooks. Raw SQL/dynamic lookup, deserialization, file and URL surfaces were searched and sampled, but the breadth of reporting/form/table/template integrations prevents a blanket injection-safety conclusion.

### Evidence ledger

| Finding | Evidence kind | Reproduction or source |
| --- | --- | --- |
| RD-001 | Real Graphene + decorator/cache, stub optimizer/monitor | test_cache_collisions_and_permission_bypass |
| RD-002 | Generated mutation class invoked directly with real DB writes | test_reverse_set_bypasses_child_permission |
| RD-003 | Generated GraphQL execution + injected database error | test_unpaginated_retry_drops_filters |
| RD-004 | Real schema/client from repository's synthetic tenancy fixture | test_tenant_header_selects_any_tenant |
| RD-005 | RequestFactory/helper/API authentication trace; no browser | test_csrf_fake_bearer_with_existing_session |
| RD-006 | Real SavedFilter model + filter pipeline | test_private_saved_filter_id |
| RD-007 | Real registry and compiled builders | test_registry_reregister_keeps_old_builder |
| RD-008 | Temporary importable app package + discovery | test_discovery_does_not_import_schema_module |
| RD-009 | Actual helper, synthetic lazy manager error | test_database_discovery_lazy_exception |
| RD-010 | Generated schema + actual consumer; mocked channel/send | test_subscription_consumer_registers_no_groups |
| RD-011 | Supported custom step + real mutation transaction | test_aborted_custom_pipeline_commits_write |
| RD-012 | Runtime inventory + authoritative Django advisory/range | Links in RD-012; no upload exploit |
| RD-013 | Static complete workflow execution trace | tag-release.yml and ci.yml; no remote release attempted |
| Performance | Synthetic related-list query count and six timings | test_query_count_baseline |

The temporary directory contains unit.log, integration.log, django.log, full.log, format-guidance.log, format-existing.log, repros-final.log and evidence-ledger.txt. Temporary files may be removed by system cleanup; the important commands, outcomes, workload and reproduction source are preserved here. The eleven behavioral tests intentionally assert defective baseline behavior. When converting them into regressions, reverse the affected assertions to express the secure/correct result and add the boundary cases listed under each finding.

## Appendix 1. Exact temporary behavioral checks and query-count workload

Save only in an isolated snapshot as audit_checks.py. This is audit evidence, not a proposed test-file addition or framework change. Run it with the environment in section C. It creates synthetic records in the test database and mocks external I/O. Repeated test names and the product variable in the Post benchmark reflect the actual verification source.

```python
import asyncio
import importlib
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import graphene
import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import RequestFactory
from graphql import GraphQLError, parse

from test_app.models import Category, Product
from rail_django.core.settings import MutationGeneratorSettings, QueryGeneratorSettings, SubscriptionGeneratorSettings
from rail_django.generators.types import TypeGenerator
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.mutations import MutationGenerator

pytestmark = pytest.mark.django_db

def test_discovery_does_not_import_schema_module(tmp_path, monkeypatch):
    from rail_django.core.registry.discovery import _discover_app_schemas
    pkg = tmp_path / "audit_app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "schema.py").write_text('SCHEMA_CONFIG = {"name": "audit_discovered"}')
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = Mock()
    _discover_app_schemas(registry, NS(name="audit_app"))
    assert registry.register_schema.call_count == 0
    importlib.import_module("audit_app.schema")
    _discover_app_schemas(registry, NS(name="audit_app"))
    assert registry.register_schema.call_count == 1
    print("DISCOVERY: fresh module missed; explicitly imported module discovered")

def test_database_discovery_lazy_exception():
    from rail_django.core.registry.discovery import _register_schemas_from_database
    class LazyRows:
        def __iter__(self):
            raise OperationalError("synthetic missing table")
    model = NS(objects=NS(all=lambda: LazyRows()))
    with patch("rail_django.core.registry.discovery.apps.get_model", return_value=model):
        with pytest.raises(OperationalError, match="synthetic"):
            _register_schemas_from_database(Mock())
    print("DISCOVERY: lazy database error escapes intended handler")

def test_cache_collisions_and_permission_bypass(monkeypatch):
    from rail_django.extensions.optimization.decorators import optimize_query
    from rail_django.extensions.query_cache import InMemoryQueryCacheBackend
    backend = InMemoryQueryCacheBackend()
    optimizer = NS(config=NS(enable_query_caching=True, query_cache_user_specific=False, query_cache_scope="schema"))
    monkeypatch.setattr("rail_django.extensions.optimization.decorators.get_optimizer", lambda *a: optimizer)
    monkeypatch.setattr("rail_django.extensions.optimization.decorators.get_performance_monitor", lambda *a: Mock())
    monkeypatch.setattr("rail_django.core.services.get_query_cache_backend", lambda *a: backend)
    calls = []
    class Query(graphene.ObjectType):
        secret = graphene.String(value=graphene.String())
        @optimize_query()
        def resolve_secret(root, info, value):
            calls.append(value)
            if not info.context.user.allowed:
                raise GraphQLError("denied")
            return value
    schema = graphene.Schema(query=Query)
    admin = NS(schema_name="audit_cache", user=NS(id=1, is_authenticated=True, allowed=True))
    denied = NS(schema_name="audit_cache", user=NS(id=2, is_authenticated=True, allowed=False))
    a = schema.execute('{ a: secret(value:"A") b: secret(value:"B") }', context_value=admin)
    assert a.errors is None and a.data == {"a": "A", "b": "A"}
    b = schema.execute('{ a: secret(value:"A") b: secret(value:"B") }', context_value=denied)
    assert b.errors is None and b.data == a.data and calls == ["A"]
    backend._store.clear()
    x = schema.execute('{ secret(value:"A") }', context_value=admin)
    y = schema.execute('{ secret(value:"B") }', context_value=admin)
    assert x.data == y.data == {"secret": "A"}
    print("CACHE: aliases collide; denied second user gets cached value; equal-length documents collide")
    print("AST string:", str(parse('{ secret(value:"A") }').definitions[0]))

def test_private_saved_filter_id():
    from rail_django.extensions.filters.models import SavedFilter
    from rail_django.generators.queries.base import QueryFilterPipeline
    owner = get_user_model().objects.create_user(username="audit_owner")
    stranger = get_user_model().objects.create_user(username="audit_stranger")
    saved = SavedFilter.objects.create(name="private_rule", model_name="Product", filter_json={"name": {"eq": "A"}}, created_by=owner, is_shared=False)
    pipeline = QueryFilterPipeline(NS(model=Product, info=NS(context=NS(user=stranger))))
    assert pipeline._load_saved_filter("private_rule") is None
    assert pipeline._load_saved_filter(str(saved.pk)).pk == saved.pk
    print("SAVED FILTER: stranger rejected by name, accepted by ID")

def test_reverse_set_bypasses_child_permission():
    from rail_django.testing import override_rail_settings
    with override_rail_settings(global_settings={"security_settings": {"enable_abac": False}}):
        category = Category.objects.create(name="Parent")
        child = Product.objects.create(name="Child", price=1, category=category)
        user = NS(is_authenticated=True, is_superuser=False, has_perm=lambda p: p == "test_app.change_category")
        info = NS(context=NS(user=user, META={}))
        ms = MutationGeneratorSettings()
        generator = MutationGenerator(TypeGenerator(mutation_settings=ms), settings=ms)
        mutation = generator.generate_update_mutation(Category)
        denied = mutation.mutate(None, info, id=str(category.pk), input={"products": {"disconnect": [str(child.pk)]}})
        assert not denied.ok
        child.refresh_from_db()
        assert child.category_id == category.pk
        allowed = mutation.mutate(None, info, id=str(category.pk), input={"products": {"set": []}})
        assert allowed.ok, allowed.errors
        child.refresh_from_db()
        assert child.category_id is None
        print("REVERSE SET: same user denied disconnect but set:[] detached child")

def test_csrf_fake_bearer_with_existing_session():
    from rail_django.utils.csrf import enforce_csrf_for_session_auth
    from rail_django.http.api.views.base import BaseAPIView
    request = RequestFactory().post("/api/v1/management/", data="{}", content_type="application/json")
    request.user = NS(is_authenticated=True)
    assert enforce_csrf_for_session_auth(request).status_code == 403
    request.META["HTTP_AUTHORIZATION"] = "Bearer definitely-invalid"
    assert BaseAPIView()._authenticate_request(request) is None
    assert enforce_csrf_for_session_auth(request) is None
    print("CSRF: invalid bearer header bypasses CSRF while session identity remains authenticated")

def test_subscription_consumer_registers_no_groups():
    from rail_django.generators.subscriptions import SubscriptionGenerator
    from rail_django.extensions.subscriptions.consumer import RailGraphqlWsConsumer
    generator = SubscriptionGenerator(TypeGenerator(), settings=SubscriptionGeneratorSettings(enable_subscriptions=True, discover_models=True))
    fields = generator.generate_model_subscriptions(Category)
    subscription = type("AuditSubscription", (graphene.ObjectType,), fields)
    class Query(graphene.ObjectType):
        ping = graphene.String()
    consumer = RailGraphqlWsConsumer()
    consumer.schema = graphene.Schema(query=Query, subscription=subscription)
    consumer.scope = {"user": NS(is_authenticated=True, is_superuser=True)}
    consumer.channel_layer = NS(group_add=AsyncMock())
    consumer.channel_name = "audit.channel"
    consumer.send_json = AsyncMock()
    asyncio.run(consumer.handle_subscribe({"id": "1", "payload": {"query": "subscription { categoryCreated { id event } }"}}))
    assert consumer._subscriptions["1"]["groups"] == []
    assert consumer.channel_layer.group_add.call_count == 0
    print("SUBSCRIPTION: valid generated operation registers zero channel groups")

def test_unpaginated_retry_drops_filters(monkeypatch):
    Product.objects.create(name="visible", price=1)
    Product.objects.create(name="hidden", price=2)
    generator = QueryGenerator(TypeGenerator(), settings=QueryGeneratorSettings(enable_pagination=False, require_model_permissions=False))
    original = generator.optimizer.optimize_queryset
    monkeypatch.setattr(generator.optimizer, "optimize_queryset", lambda qs, *a: qs.prefetch_related("category").extra(select={"bad": "audit_missing_column"}))
    field = generator.generate_list_query(Product)
    class Query(graphene.ObjectType):
        products = field
    schema = graphene.Schema(query=Query)
    ctx = NS(schema_name="default", user=NS(is_authenticated=True, is_superuser=True), META={})
    result = schema.execute('{ products(where:{name:{eq:"visible"}}) { name } }', context_value=ctx)
    assert not result.errors, result.errors
    assert {p["name"] for p in result.data["products"]} == {"visible", "hidden"}
    print("RETRY: forced related-query OperationalError returns hidden row despite where filter")

def test_aborted_custom_pipeline_commits_write():
    from rail_django.generators.pipeline.base import MutationStep, MutationPipeline
    from rail_django.generators.pipeline.factories.base import BasePipelineMutation
    class WriteThenReject(MutationStep):
        order = 80
        name = "write_then_reject"
        def execute(self, ctx):
            ctx.result = Category.objects.create(name="should_rollback")
            ctx.add_error("Synthetic business rule rejected")
            return ctx
    class Rejected(BasePipelineMutation):
        model_class = Category
        operation = "create"
        pipeline = MutationPipeline([WriteThenReject()])
        @classmethod
        def build_response(cls, ctx):
            return cls(ok=not ctx.should_abort, errors=ctx.errors)
    response = Rejected.mutate(None, NS(context=NS(user=None)), input={})
    assert response.ok is False
    assert Category.objects.filter(name="should_rollback").exists()
    print("PIPELINE: ok:false with should_abort still commits earlier write")

def test_tenant_header_selects_any_tenant():
    from tests.unit.test_multitenancy import TestMultiTenancy
    case = TestMultiTenancy()
    case.setUp()
    query = "{ tenantProjectList { name } }"
    a = case._client(case.org1.id).execute(query)
    b = case._client(case.org2.id).execute(query)
    assert a["data"]["tenantProjectList"] == [{"name": "Project 1"}]
    assert b["data"]["tenantProjectList"] == [{"name": "Project 2"}]
    print("TENANT: same ordinary model-authorized user can select either tenant by header")

def test_registry_reregister_keeps_old_builder():
    from rail_django.core.registry import SchemaRegistry
    registry = SchemaRegistry()
    registry.register_schema("audit_reregister", apps=["test_app"], models=["test_app.Category"], auto_discover=False)
    first = registry.get_schema_instance("audit_reregister")
    registry.register_schema("audit_reregister", apps=["test_app"], models=["test_app.Product"], auto_discover=False)
    second = registry.get_schema_instance("audit_reregister")
    assert first is second
    print("REGISTRY: re-register models returns identical old GraphQL schema instance")
    registry.clear()

def test_query_count_baseline():
    import json, time, statistics
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from test_app.models import Tag, Post
    categories = [Category.objects.create(name=f"Cat {i}") for i in range(10)]
    tags = [Tag.objects.create(name=f"Tag {i}") for i in range(3)]
    for i in range(100):
        product = Post.objects.create(title=f"Post {i}", category=categories[i % 10])
        product.tags.add(tags[i % 3])
    generator = QueryGenerator(TypeGenerator(), settings=QueryGeneratorSettings(default_page_size=50, max_page_size=100, require_model_permissions=False), schema_name="audit_perf")
    class Query(graphene.ObjectType):
        products = generator.generate_list_query(Post)
    schema = graphene.Schema(query=Query)
    query = "{ products(limit:50) { title category { name } tags { name } } }"
    measures = []
    for i in range(6):
        ctx = NS(schema_name="audit_perf", user=NS(is_authenticated=True, is_superuser=True), META={})
        start = time.perf_counter()
        with CaptureQueriesContext(connection) as capture:
            result = schema.execute(query, context_value=ctx)
        assert not result.errors, result.errors
        assert len(result.data["products"]) == 50
        measures.append({"ms": round((time.perf_counter()-start)*1000,3), "queries":len(capture)})
    print("PERF optimized list 100 rows / 10 FK / 3 tags / 50 returned:", json.dumps(measures))
    print("PERF warm median ms:", statistics.median(m["ms"] for m in measures[1:]))
```

## Appendix 2. Python network guard used for local checks

The guard was saved as guard/sitecustomize.py before test execution. It permits stdlib internal socketpair construction and blocks normal outbound Python connects. It does not control native subprocesses.

```python
import os, socket, sys
os.environ['ENVIRONMENT'] = 'testing'
os.environ['DJANGO_DEBUG'] = 'False'
_original_connect = socket.socket.connect
def blocked_connect(self, address):
    caller = sys._getframe(1)
    if caller.f_code.co_name == 'socketpair' and caller.f_globals.get('__name__') == 'socket':
        return _original_connect(self, address)
    raise RuntimeError('Audit isolation: network connections are disabled')
def blocked(*args, **kwargs):
    raise RuntimeError('Audit isolation: network connections are disabled')
socket.socket.connect = blocked_connect
socket.socket.connect_ex = blocked
socket.create_connection = blocked
```
