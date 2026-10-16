# Rail Django prioritized implementation plan

Implementation progress and verification are recorded in [rail-django-implementation-status.md](rail-django-implementation-status.md). The plan below retains the original audit baseline and intended release gates.

Prepared 16 October 2026 against revision `fbca6deb21d93c347e47af86fbcdd2d8e5844fa3`. This plan accompanies the [audit report](E:/Projects/libraries/rail-django/docs/audits/rail-django-audit.md). Finding IDs refer to that report. No implementation or dependency change has been made.

The immediate objective is to close verified authorization gaps and preserve the framework's valid public behavior. Treat each security correction as an explicit behavior change: formerly unauthorized successes must stop, while permitted operations, field names, payloads and supported hooks remain stable wherever possible. Do not claim full compatibility from internal tests alone.

## Priorities and delivery shape

| Order | Work item / finding | Intended result | Size and dependency |
| --- | --- | --- | --- |
| 0 | B-01: reproducible baseline and consumer contract fixtures | Known versions, real HTTP security coverage, saved public/schema contracts | 1–2 days; starts immediately |
| 0 | B-02 / RD-013: release gate | Publish only tested, successfully built revisions | 0.5–1.5 days; independent |
| 1 | S-01 / RD-012: patched supported dependency baseline | Remove verified affected runtime from deployment guidance | 1–2 days plus consumer upgrades; support decision |
| 1 | S-02 / RD-001: contain unsafe result caching | Cache hits cannot skip resolver authorization | 1–2 days containment; safe re-enablement is separate |
| 1 | S-03 / RD-002: authorize reverse set detach | Equivalent nested operations enforce child access | 1–2 days |
| 1 | S-04 / RD-003: preserve query scope on failure | No database-error fallback returns broader rows | 0.5–1.5 days |
| 1 | S-05 / RD-004: validate tenant selection | Header selection requires a trusted authorization boundary | 2–4 days plus coordinated consumer rollout |
| 1 | S-06 / RD-005: authenticate before CSRF exemption | Cookie/session identity retains CSRF protection | 1–2 days |
| 1 | S-07 / RD-006: consistent saved-filter access | ID and name use the same visibility/model rule | 0.5–1 day |
| 1 | S-08 / RD-011: rollback returned pipeline errors | Failed atomic mutations leave no partial database write | 0.5–1 day |
| 2 | P-01: establish broader measured workloads | Evidence to accept or reject performance work | 1–2 days; after relevant correctness fixes |
| 2 | P-02 / RD-001: limited safe cache restoration, only if justified | Equivalent authorized cached results with bounded storage/invalidation | 1–2 additional days or defer |
| 3 | M-01 / RD-007: rebuild on schema-shaping registration | Registration updates actually change served schema | 1–3 days; extension-lifetime decision |
| 3 | M-02 / RD-008: real module discovery | Ordinary app schema modules import deterministically | 0.5–1 day |
| 3 | M-03 / RD-009: lazy database discovery recovery | Specific availability errors handled at evaluation | 0.5–1 day; required/optional policy |
| 3 | M-04: focused documentation and package/scaffold checks | Accurate support/setup/extension guidance | 0.5–1 day plus affected PR documentation |
| 4 | D-01 / RD-010: secure working subscriptions | Generated operations register and deliver authorized events | 3–5 days; protocol/tenant decision and live local transport |
| Separate decision | D-02: support-policy removal or public contract changes | Explicit deprecation/major-release treatment when required | Estimate only after maintainer decisions |

Estimates are engineering days for focused work and review preparation, not a calendar commitment. Consumer coordination, unknown hook behavior, database provisioning and CI queue time are additional. Avoid a combined refactor PR. Each item below is independently reviewable unless its dependency is stated.

## Phase 0: baseline and missing verification

### B-01. Build a reproducible baseline and preserve public contracts

**Problem/outcome.** The existing local suite passes on Python 3.11.0/Django 5.2.13/SQLite, but the runtime includes a verified affected Django version, clean dependency resolution was not tested, marker coverage is incomplete and the schema harness does not automatically exercise the HTTP middleware stack. Establish exactly what each proposed fix preserves.

**Scope.** [pyproject.toml](E:/Projects/libraries/rail-django/pyproject.toml:1), [.github/workflows/ci.yml](E:/Projects/libraries/rail-django/.github/workflows/ci.yml:1), [pytest.ini](E:/Projects/libraries/rail-django/pytest.ini:1), [rail_django/config/test_settings.py](E:/Projects/libraries/rail-django/rail_django/config/test_settings.py:1), [rail_django/config/framework_settings.py](E:/Projects/libraries/rail-django/rail_django/config/framework_settings.py:1), [rail_django/testing/harness.py](E:/Projects/libraries/rail-django/rail_django/testing/harness.py:1), public __init__ exports, representative example models and tests. Consumer fixtures require separate authorized read access; do not modify applications to produce a passing baseline.

**Steps.**

1. Record clean/dirty Git state, revision and resolved packages for every run. Resolve fresh virtual environments for maintained minimum/current Python/Django combinations. Use ephemeral SQLite and PostgreSQL databases; add MySQL only if it is confirmed supported.
2. Capture `pytest -q -rs`, marker runs and the Django runner, with exact skipped node IDs/reasons. Reconcile documented Black command with real files. Keep unrelated formatting out of security PRs.
3. Build wheel/sdist using isolated build dependencies, install them into an empty environment, import public symbols and run `rail-admin startproject` in a temporary directory. Boot only with local test settings; no generated secret values in logs.
4. Save a small public-contract fixture: import paths/signatures/return types, default and configured schema introspection, metadata settings precedence and stored operations. Include custom mutation/hook/service extensions, two schemas, nullable/default/scalar/enum fields, omitted/null inputs and legacy input-type arguments.
5. Port each audit reproduction into an actual failing regression for its proposed correction, one PR at a time. The appendix checks currently assert the defect and must be inverted. Use a CSRF-enforcing Django client for HTTP and a live local Channels communicator for transport; direct Graphene/mutate calls alone are insufficient.
6. Add an authorized representative consumer operation replay when available. Capture payload/error/side-effect differences, not just whether execution returns without exception.

**Acceptance and compatibility.** A versioned baseline identifies passes, failures, skips and blocked combinations. All new findings have a regression that fails before its patch and passes after. Public import/schema snapshots show expected differences only. Record known baseline formatting/support failures separately; do not claim a green minimum-version matrix until executed.

**Documentation/release.** Update testing instructions to actual paths and isolation commands. Attach package inventories and test logs to the implementation PRs. This is an internal/additive verification change; changing helper defaults or injecting middleware globally would be observable and is outside this item.

**Deployment/rollback.** Test-only fixtures and isolated builds need no production migration. If CI provisioning fails, mark that combination unverified rather than silently removing it. Effort 1–2 days initially; continued checks are part of each following PR. Risk is accidentally treating synthetic fixtures as consumer proof.

### B-02. Gate release publication on the tested commit (RD-013)

**Problem/outcome.** The release job can tag before tests/build succeed. Publication must require successful checks and artifacts for the exact SHA.

**Scope.** [.github/workflows/tag-release.yml](E:/Projects/libraries/rail-django/.github/workflows/tag-release.yml:1), [.github/workflows/ci.yml](E:/Projects/libraries/rail-django/.github/workflows/ci.yml:1) and the existing package-build workflow; release documentation, SCM version/tag conventions and Actions token permissions.

**Steps.**

1. Select a shared validation workflow/job dependency or verified completed-CI trigger. Bind commit, branch and event provenance explicitly; do not publish the current branch tip when a previous SHA passed.
2. Run/consume the required test matrix and wheel/sdist smoke checks before tagging. Build and verify artifacts first.
3. Preserve current tag/version semantics, handle existing tags/releases idempotently and grant write permission only to publication.
4. Exercise failure and retry cases in a nonpublishing dry run. Do not make a live tag merely to test the workflow.

**Checks/acceptance.** A failed test or build creates no tag/release; successful publication uses the checked SHA; reruns avoid duplicate or mismatched artifacts. Review push/manual/untrusted event selection and any branch protections. No framework API/schema change is intended.

**Release/operations.** Document required checks, version calculation and recovery from an existing orphaned tag. Deploy the workflow independently before runtime releases. Roll back workflow mechanics only while retaining a test gate; manually verify SHAs if automation is temporarily unavailable. Effort 0.5–1.5 days; depends on maintainer release permissions, with no application migration.

## Phase 1: urgent security and correctness fixes

### S-01. Establish a patched supported runtime (RD-012)

**Problem/outcome.** The audit environment's Django 5.2.13 is within the confirmed CVE-2026-5766 range. Support metadata and docs disagree. Establish a maintained patched runtime without mixing in an unreviewed major/minor upgrade.

**Scope.** pyproject dependency constraints/classifiers, scaffold requirements, CI matrix and installation/deployment docs; packaging and generated ASGI/GraphQL projects. Deployment lockfiles belong to their owners and require their own authorized update.

**Steps.**

1. Verify current Django advisories and supported patch series when implementing. Do not treat 5.2.14, the first fix for this advisory, as a permanent security target.
2. Resolve and run B-01 on the selected maintained patched series. Compare schema, operations, errors and package import behavior with the audited baseline.
3. Reconcile declared floors and supported series across pyproject, templates and docs. Decide separately whether to remove obsolete 5.0/5.1 support; a package constraint change affects existing installations.
4. Run a dependency advisory scan on the actual resolved environment/authorized lockfiles. Verify advisory ranges and reachability before adding further findings.
5. Test ASGI upload/body limits with a bounded local request workload. Confirm application and upstream server limits without a large destructive upload.

**Acceptance.** Supported/deployed constraints no longer resolve the verified affected version; clean package/scaffold checks and agreed version matrix pass; any remaining legacy support is explicitly documented with its security limitations. Do not infer all dependencies are safe from this one fix.

**Compatibility/release.** Security dependency correction. Patch compatibility must be shown by tests and consumer replay. Dropping a Django series is a separate breaking support-policy decision (D-02). Publish exact tested versions and resolved constraints.

**Deployment/rollback.** Stage upgrades with application owners, retain a known compatible supported patched fallback, and verify rollback does not select an affected version. No library data migration is expected solely from a Django patch; check release notes before asserting that. Effort 1–2 days excluding consumer remediation; dependency on support-policy choice.

### S-02. Stop result-cache hits bypassing authorization (RD-001)

**Problem/outcome.** The decorator returns before the security-bearing resolver, and keys omit invocation identity. The first PR must prevent unauthorized cached success.

**Scope.** [rail_django/extensions/optimization/decorators.py](E:/Projects/libraries/rail-django/rail_django/extensions/optimization/decorators.py:108), [rail_django/extensions/optimization/cache.py](E:/Projects/libraries/rail-django/rail_django/extensions/optimization/cache.py:41), generated list resolver callers, query-cache backend/service registration and caching docs/tests. Inventory custom optimize_query users and all settings enabling result caching.

**Steps.**

1. Add alias/argument/document collision and two-user permission-revocation regressions with the actual decorator and backend.
2. Bypass result caching for protected resolvers whose authorization cannot run before lookup. Keep the decorator signature and optimizer/monitor behavior intact; do not insert a second incomplete permission policy.
3. Verify generated materialized-list results and custom decorated results are covered. Existing QuerySet noncache behavior must remain understood.
4. Clear/version incompatible existing entries. Keep default caching off. Defer safe cache restoration to P-02, which requires complete invocation identity and invalidation.

**Acceptance.** A denied user never receives a cached authorized response; a changed argument/alias returns its own result; permitted cached/uncached executions have equivalent response/error contracts. All expected outer and resolver permission checks still run. Do not accept a key-only patch as authorization repair.

**Compatibility/documentation.** Security correction: hit rates, resolver counts and latency may change. Release notes state which cache paths are bypassed and how users migrate; no insecure compatibility flag. Existing user-specific key settings do not solve revocation or tenant switching.

**Deployment/rollback.** First contain affected cache configurations in deployments that enable them. Flush namespace/version on rollout across workers. Rollback may restore optimizer mechanics while keeping unsafe result caching disabled. Effort 1–2 days for containment; remaining safe-cache work may bring total RD-001 effort to 2–4 days. No schema/data migration intended.

### S-03. Authorize every child removed by reverse set (RD-002)

**Problem/outcome.** Nullable reverse-FK set currently uses a direct bulk detach that skips child update checks. Equivalent set/disconnect operations must enforce the same policy and atomicity.

**Scope.** [handle_set](E:/Projects/libraries/rail-django/rail_django/generators/nested/handler.py:513), _resolve_related_instance/_ensure_operation_access/_save_instance, [rail_django/generators/nested/operations.py](E:/Projects/libraries/rail-django/rail_django/generators/nested/operations.py:79), create/update and bulk callers, relation input exposure/metadata and test models with nullable/non-nullable FKs. No new input field is needed.

**Steps.**

1. Reproduce parent-only permission with disconnect denied and set:[] accepted. Add object-guard and cross-tenant child cases.
2. Compute the removal set, resolve and authorize all removed children before changing links. Reuse the same update/tenant path used by explicit disconnect.
3. Apply validated child saves or demonstrate equivalent full_clean/signal semantics; document any hook change. Keep non-nullable rejection and retained/added-child behavior.
4. Ensure denial or a later failure rolls back every child link under existing outer transaction entry points.
5. Record query/signal counts for 1, 10 and 100 removals; any later bulk optimization must preserve every check.

**Acceptance.** Parent access alone cannot detach unauthorized children. Mixed authorized/denied sets make no changes; same-tenant allowed operations still work; all shared generated and bulk callers pass regression tests.

**Compatibility/release.** Security correction with no intended schema change. Existing callers can newly receive a permission error; validated saves may trigger hooks that the old bulk update skipped. Publish both effects and review consumer signals/external side effects.

**Deployment/rollback.** No data migration required for the logic; do not silently reconstruct previously detached links without a separate data investigation. If hook regressions require rollback, restrict the unsafe set operation rather than reinstate unchecked detachment. Effort 1–2 days; risk is extra query/hook work, measured separately.

### S-04. Preserve all query restrictions on database failure (RD-003)

**Problem/outcome.** An unpaginated optimized-read retry starts from manager.all and loses filters/custom ownership scope. Failure must preserve the requested scope or return a sanitized error.

**Scope.** [generate_list_query](E:/Projects/libraries/rail-django/rail_django/generators/queries/list.py:190), both paginated/unpaginated exception branches, optimizer related-loading helper, QueryFilterPipeline and custom list resolver hooks; schema-error classification and tests.

**Steps.**

1. Add the injected related-query error test with pagination off/on and assert filtered rows remain excluded.
2. Prefer removing the permissive retry and using the existing sanitized error path. If a retry is retained, clone the already scoped queryset and clear only related-loading optimizations.
3. Preserve custom queryset restrictions, tenant scope, where/basic/preset/saved filters, ordering and property-order results. Avoid invoking stateful pipeline helpers twice.
4. Narrow any schema-error classification only if needed for the chosen retry; do not add a broad recovery abstraction.
5. Verify PostgreSQL transaction/savepoint behavior after query errors so a retry does not operate in an aborted transaction.

**Acceptance.** No injected failure expands returned IDs under any tested filter/tenant/owner combination. Permitted successful results, ordering and error sanitization remain stable; duplicate usage/audit side effects do not occur.

**Compatibility/release.** Security correction: errors may replace formerly broadened successful responses. Publish the behavior and migration/repair guidance. No GraphQL schema change or application data migration is expected.

**Deployment/rollback.** Roll out the safe error behavior first; repair missing schema/migrations through application procedures. A rollback must retain safe failure or disable the affected unpaginated path. Effort 0.5–1.5 days; PostgreSQL verification is a release gate, not an inferred SQLite result.

### S-05. Establish trusted tenant selection (RD-004)

**Problem/outcome.** A client header identifies a tenant without proving the user may select it. Preserve legitimate multi-tenant workflows while requiring an authorization boundary.

**Scope.** [rail_django/extensions/multitenancy/resolver.py](E:/Projects/libraries/rail-django/rail_django/extensions/multitenancy/resolver.py:102), settings/coercion, queryset and mutation applicators, request/JWT middleware, schema-specific settings and multitenancy documentation. Existing model permissions remain additional controls.

**Steps.**

1. Inventory supported request.tenant_id, verified JWT and proxy integrations. Define the trusted-source precedence and policy for superusers/multi-tenant users.
2. Reject unvalidated client-header scope. Use existing authenticated context or verified claims where possible.
3. If header switching is required, introduce the smallest explicit application authorization callback or trusted-proxy contract. Never invent a universal membership model or accept a callback result without request identity.
4. Add an explicit way to disable header fallback; fix empty-string coercion only according to the documented setting contract.
5. Test same user against two tenants, allowed switching, revoked membership, forged/absent context, claim/header conflict, queries/nested/bulk mutations and two schemas. Extend import/export tests where the same tenant integration is supported.
6. Replace misleading blanket 404/isolation examples with actual operation-specific results and the external trust requirement.

**Acceptance.** Changing only a caller-supplied tenant header cannot grant another tenant's data/operations. Authorized selection works through the chosen integration. Missing or failed validation fails closed with documented errors. Membership work may be reused within one request only after identity is established.

**Compatibility/release.** Security correction with a potentially breaking client integration change; an added callback itself requires configuration compatibility tests. Provide a concrete migration guide mapping old header-only clients to trusted context/verified claims or validated switching. Coordinate deployment, not indefinite insecure fallback.

**Deployment/rollback.** Prepare consumer/proxy membership validation before enforcing the corrected resolver; contain unprotected endpoints during transition. Rollback must keep an equivalent external membership boundary or disable tenant-selected access. No membership data migration should be invented by the library. Effort 2–4 days plus consumer coordination; maintainer trust-contract decision required.

### S-06. Use validated authentication provenance for CSRF (RD-005)

**Problem/outcome.** A dummy bearer header can suppress CSRF while an existing session identity is accepted. Exempt only credentials actually validated and used.

**Scope.** [rail_django/utils/csrf.py](E:/Projects/libraries/rail-django/rail_django/utils/csrf.py:27), [rail_django/http/api/views/base.py](E:/Projects/libraries/rail-django/rail_django/http/api/views/base.py:82), active [rail_django/graphql/views/multi_schema/view.py](E:/Projects/libraries/rail-django/rail_django/graphql/views/multi_schema/view.py:133), JWT header/cookie middleware and auth_method assignment, HTTP auth docs, CORS/session fixtures.

**Steps.**

1. Add real CSRF-enforcing Django client tests for session-only and invalid bearer plus session on REST and GraphQL.
2. Record validated identity provenance in the existing authentication flow. If session identity is retained, enforce session CSRF; do not trust header syntax.
3. Decide invalid-header-plus-session precedence. Keep valid header-only token clients working and preserve JWT cookie CSRF enforcement.
4. Cover safe methods, multipart, missing/invalid tokens, expired/revoked identities, allowed/disallowed origins and response envelopes.

**Acceptance.** No-token session requests with a forged header fail CSRF/authentication. Valid explicit header-token requests follow the documented exemption; cookie-authenticated requests remain protected. Tests demonstrate both actual HTTP entry points, not just the utility function.

**Compatibility/release.** Security correction; dummy/stale Authorization plus cookies may start returning 401/403. Document identity precedence and required CSRF client behavior. Do not present this as an unconditional arbitrary-origin attack.

**Deployment/rollback.** Coordinate stale-header cleanup in frontends. Observe aggregate failure rates without logging credentials. Rollback must continue CSRF enforcement for the identity actually used. Effort 1–2 days; auth owner review required, no data migration.

### S-07. Share saved-filter visibility logic for ID and name (RD-006)

**Problem/outcome.** Private/model restrictions are applied only to name lookup. Numeric identifiers must use identical visibility rules.

**Scope.** [QueryFilterPipeline._load_saved_filter](E:/Projects/libraries/rail-django/rail_django/generators/queries/base.py:174), usage-stat update, SavedFilter model and compatibility import, generated list/page callers, [tests/integration/test_saved_filters.py](E:/Projects/libraries/rail-django/tests/integration/test_saved_filters.py:1) and saved-filter docs.

**Steps.**

1. Build one model-scoped queryset constrained to shared filters or current ownership, then select by numeric ID or name.
2. Preserve current inaccessible/nonexistent filter behavior; do not add unrelated GraphQL error/schema changes.
3. Ensure unavailable filters do not update usage statistics.
4. Add owner/non-owner/anonymous × shared/private × ID/name cases and another-model IDs for both list/page callers.

**Acceptance.** A stranger's private ID behaves like its private name; authorized IDs/names retain the same filter results; no inaccessible usage updates. Query count remains bounded.

**Compatibility/release.** Security correction; formerly unauthorized numeric IDs stop applying. No database/schema migration expected. Keep model-name/app-label redesign outside this PR.

**Deployment/rollback.** Publish visibility tightening. If consumers used private cross-user IDs, make the intended filters shared or correctly owned through their normal authorized process. Do not restore bypass on rollback. Effort 0.5–1 day, independent of other security patches.

### S-08. Roll back pipelines that return abort state (RD-011)

**Problem/outcome.** Custom mutation steps can write then add_error, return ok:false and still commit. Handle returned aborts at the shared transaction boundary.

**Scope.** [BasePipelineMutation.mutate](E:/Projects/libraries/rail-django/rail_django/generators/pipeline/factories/base.py:121), MutationContext.should_abort/add_error/add_errors, CRUD response builders, custom PipelineBuilder entry points and [tests/unit/test_pipeline_transactions.py](E:/Projects/libraries/rail-django/tests/unit/test_pipeline_transactions.py:1). Search alternate pipeline invocations and bulk/nested wrappers before patching.

**Steps.**

1. Add write-then-add_error and later-rejecting-step regressions with real transaction state.
2. After execute_pipeline, mark the current atomic block for rollback when should_abort is true before building the response.
3. Keep warnings non-aborting. Preserve exception rollback and success response shape.
4. Test create/update/delete, add_errors, nested and caller-owned atomic blocks, later validation failure and on_commit callback suppression.
5. Inventory audit/event callbacks: defer success effects until commit where required, while keeping intentional attempted-operation audit semantics explicit.

**Acceptance.** ok:false caused by abort leaves database state unchanged; warning-only success commits; exceptions and supported payload details remain stable. External effects are either suppressed until commit or explicitly documented as attempt logging.

**Compatibility/release.** Observable bug fix; consumers relying on partial writes after an error response change behavior. Document atomic failure and safe retry behavior. Do not broadly redesign pipelines.

**Deployment/rollback.** No automatic repair of historic partial rows. Investigate any consumer reconciliation separately. If rollback is needed, disable affected custom write-then-abort flows instead of accepting silent commits. Effort 0.5–1 day plus any discovered external-effect work.

### Phase 1 release gate

Each security/transaction PR must include its regression through the shared root cause and affected public entry points, a compatibility classification, expected response differences and release notes. Run the full suite on the agreed maintained matrix, package/scaffold smoke tests and relevant PostgreSQL transaction tests. Assert GraphQL schema/import contracts are unchanged where no schema change is intended. Replay authorized and denied consumer operations when available.

For RD-001–RD-006, a passing helper test alone is insufficient: include the relevant generated/HTTP integration and two-user/tenant cases. For RD-011, assert both persisted rows and commit-dependent effects. If consumer replay is unavailable, explicitly record that gap and avoid a universal compatibility claim. Retain the unsafe feature disabled if its security gate fails.

## Phase 2: measured performance improvements

### P-01. Extend the query/resource baseline before optimizing

**Problem/outcome.** The audit found no general measured N+1 defect: a 50-row nested list made two queries. Other potentially expensive paths remain unmeasured. Establish enough evidence to justify a specific small optimization.

**Scope.** Existing optimizer/monitor and profile_graphql_queries management command; generated lists/page/count/property filters, nested mutations, export/import services and representative metadata/security fixtures. Add focused benchmark/test workloads rather than a new benchmark framework or dependency.

**Steps.**

1. Preserve the audit's 100-Post/10-Category/3-Tag workload as a query-count guard, using actual model/field names in the permanent test. Include ordinary policy-bearing users in an additional case.
2. Profile 10/100/1,000 returned or processed objects where existing caps permit, with FK/M2M selections, property ordering, exact/estimated counts and real permission checks. Use separate tests for page-size enforcement rather than removing caps.
3. Measure 1/10/100 child detach operations after S-03, including authorization/save hooks. Measure export/import memory and row caps at bounded sizes on local resources.
4. Record database version, schema/indexes, dataset, warm/cold definition, repetitions, SQL/query counts, CPU/time and peak memory. Avoid percentiles from six samples; use adequate repetitions if percentile reporting is needed.
5. Select only a demonstrated repeated query/materialization/reflection cost. Reuse existing select_related/prefetch/.only/settings helpers where correct. Add no shared cache without identity, invalidation, revocation and memory limits.
6. Compare exact result ordering, IDs, errors and permission-check behavior before/after; report measured changes without invented speedup targets.

**Acceptance.** A performance PR identifies one measured mechanism, reproduces it and demonstrates improvement under the same workload with no observable contract difference. Otherwise publish the baseline and defer the code change. The ordinary related-list baseline should remain bounded at two relation-loading queries under its original controlled assumptions.

**Compatibility/release.** Internal optimization only when behavior is unchanged. Any change to counts, ordering caps, pagination semantics or denied results is a separate observable change and must not be hidden as optimization.

**Deployment/rollback.** Canary with existing metrics and bounded resource checks. Roll back the optimization if behavior or memory regresses, retaining security fixes. Effort 1–2 days for baseline; additional optimization estimate follows evidence. No application migration or new runtime dependency proposed.

### P-02. Restore only proven-safe cache cases, if demand justifies it (RD-001)

**Problem/outcome.** S-02 contains the authorization issue. Re-enabling caching is optional and must not weaken that correction merely to recover a hit rate.

**Scope.** Existing optimize_query decorator, key builder, backend protocol/InMemory backend, schema-version invalidation and caller inventory from S-02.

**Steps.**

1. Select a concrete resolver whose current authorization can run before lookup. If that cannot be done without splitting undocumented custom logic, keep it uncached.
2. Key the exact invocation: printed operation and fragments, coerced field arguments, parent identity when relevant, schema/version, authenticated user and trusted tenant context. Canonicalize only types already supported by the cache contract.
3. Check current permission/membership on every request. User IDs alone do not cover permission changes or switching tenants.
4. Define writes/configuration/permission invalidation, cross-worker behavior, TTL and bounded entry eviction. Avoid sharing mutable ORM instances between requests.
5. Test aliases, literals/variables, equal-length documents, fragments, different parents, two users/tenants/schemas, writes, revocation, eviction and backend errors.
6. Measure hit/miss latency and memory on the same fully authorized workload; retain only cache cases with demonstrated value.

**Acceptance.** Cached and uncached operation replay is identical for every authorized/denied test; stale entries cannot reveal a prior identity's result; storage bounds and invalidation are exercised. Backend failure has a safe documented behavior.

**Compatibility/release.** Security correction plus implementation changes; preserve decorator/import signatures. Any new backend requirement must have a documented compatibility adapter only if a real backend needs it. No universal cache abstraction or implicit public-resolver flag is justified by this audit.

**Deployment/rollback.** Version/flush old keys and roll out consistently across workers. Disable result caching as the rollback while retaining S-02. Effort 1–2 additional days; depends on caller inventory and measured need. Defer if no affected consumer needs it.

### Phase 2 release gate

No performance code merges without same-workload measurements and response/authorization equivalence. Capture resource bounds and invalidation in tests. A smaller query count achieved by removing permissions is a failure. A small SQLite improvement is not a production speedup claim.

## Phase 3: focused correctness, maintenance and documentation

### M-01. Invalidate compiled schema state on registration updates (RD-007)

**Problem/outcome.** Re-registration changes SchemaInfo but can keep the old builder's compiled schema. Model selection/exclusions/settings changes must affect the schema actually served.

**Scope.** [register_schema](E:/Projects/libraries/rail-django/rail_django/core/registry/registry.py:73), [rail_django/core/registry/builders.py](E:/Projects/libraries/rail-django/rail_django/core/registry/builders.py:1), existing _dispose_builder/signal cleanup and rebuild helpers, schema versions/snapshots, middleware/introspection caches, [rail_django/http/api/views/schema_detail.py](E:/Projects/libraries/rail-django/rail_django/http/api/views/schema_detail.py:31) and programmatic/CLI callers.

**Steps.**

1. Decide whether registration mutates/rebuilds the existing builder or replaces it. Inventory custom mutation/hooks registered after initial creation and callers retaining builder references.
2. Add the real register/build/change-models test, asserting old fields disappear and new ones appear, not only that object identity changes.
3. Invalidate every affected layer for schema-shaping changes. Reuse disposal/rebuild helpers; preserve intended custom extension lifetime and clear removed runtime settings.
4. Cover unchanged/duplicate registration, include/exclude changes, explicit empty settings, disabled schemas, version updates and signal-handler cleanup.
5. Exercise REST PUT and programmatic calls; add concurrent read/update verification and document how all workers receive the change.

**Acceptance.** Served introspection matches the latest accepted configuration. Registered extensions survive according to the agreed contract; no stale signal handlers or unintended double build remains. Existing operations differ only for intentionally changed schema definitions.

**Compatibility/release.** Observable fix: stale fields can disappear immediately, and retained builder reference behavior must be stated. Snapshot/replay consumers before rollout. An across-process coordination redesign is not part of the minimum fix.

**Deployment/rollback.** Apply/rebuild consistently across workers, with a controlled restart if that is the existing propagation mechanism. Keep the previous configuration for rollback and rebuild it deliberately. No registry-row data migration expected unless the chosen implementation changes stored shape, which would require separate review. Effort 1–3 days; maintainer extension-lifetime decision required.

### M-02. Import schema modules with the module loader (RD-008)

**Problem/outcome.** The symbol loader silently misses normal schema.py modules. Discovery should follow the documented candidate layout and expose genuine dependency errors.

**Scope.** [_discover_app_schemas](E:/Projects/libraries/rail-django/rail_django/core/registry/discovery.py:51), SCHEMA_CONFIG/register_schema hook conventions, settings/hook precedence, discovery management/API callers and app templates.

**Steps.**

1. Replace module-candidate import_string use with importlib.import_module.
2. Ignore only a missing candidate path. Distinguish it from an import failure inside a present module; report context rather than silently skipping it.
3. Preserve candidate order, first-match behavior and registration callback/SCHEMA_CONFIG handling.
4. Add temporary packages for every documented layout, empty __init__, missing modules, failing dependencies, duplicate names and repeated discovery.
5. Smoke-test a scaffolded app and compare discovered schema names/fields with representative consumers before enabling newly found modules.

**Acceptance.** A fresh app.schema is found without an incidental prior import. Genuine module errors remain diagnosable. No uncontrolled repeat hooks or unexpected precedence change.

**Compatibility/release.** Observable fix; previously ignored schemas may become active and collide or expose newly generated fields. Document this startup change and require a predeployment discovery/introspection comparison.

**Deployment/rollback.** Resolve collisions in explicit configuration before rollout. Roll back by explicitly selecting the intended schemas while retaining diagnosable imports; do not normalize silent missing-module behavior as the long-term contract. Effort 0.5–1 day; independent of M-03.

### M-03. Catch database errors when discovery evaluates rows (RD-009)

**Problem/outcome.** The current error boundary wraps lazy all() construction rather than execution. Handle expected missing-table/availability errors without masking coding errors or permanently skipping recovery.

**Scope.** [_register_schemas_from_database](E:/Projects/libraries/rail-django/rail_django/core/registry/discovery.py:87), discover_schemas initialized state, AppConfig startup and direct get_schema/discovery callers, logging and management startup guidance.

**Steps.**

1. Define optional versus required database-registry behavior. Required security-relevant definitions must not silently degrade to a different schema.
2. Place iteration/evaluation inside the OperationalError/ProgrammingError boundary while retaining per-row error handling.
3. Preserve successful app/settings registration when policy permits. Log useful context without SQL credentials or application data.
4. Define the recovery/retry trigger after migrations/outages; avoid a failing database query on every request or a permanent initialized flag after a temporary failure.
5. Test an actual temporary missing table, lazy query failure, valid rows, malformed entries, recovery and startup management commands.

**Acceptance.** Specific database failures are handled according to the declared mode; arbitrary code errors surface. Recovery registers definitions once, and requests cannot unintentionally fall back to permissive configuration.

**Compatibility/release.** Observable reliability fix. Publish optional/required startup semantics and retry behavior; adding a setting requires a demonstrated deployment distinction, not speculative flexibility.

**Deployment/rollback.** Test fresh-install/migrate order in staging. Restore the prior known configuration/startup mode if necessary; do not accept a fail-open registry. Effort 0.5–1 day; depends on the registry-required policy.

### M-04. Reconcile documentation, dependency instructions and extension contracts

**Problem/outcome.** Stale root paths, a nonexistent formatting target, conflicting install/support instructions and undocumented security/hook semantics make correct use harder.

**Scope.** AGENTS/README/CONTRIBUTING links, rail_django/docs installation/testing/configuration/security/multitenancy/subscriptions references, pyproject/template dependency lists and the actual test/CI commands. Preserve the user-requested audit files under docs/audits; do not move canonical docs solely to match old links.

**Steps.**

1. Point contributor instructions at the existing canonical documentation and current HTTP module paths.
2. Replace the missing Black target with an agreed real check; handle pre-existing harness formatting separately from urgent security diffs.
3. Explain package runtime versus scaffold application dependency sets and remove advertisements for nonexistent extras or deliberately implement only an established supported extra.
4. Document root getter class returns versus core factory instance returns, schema extension lifetime, settings precedence, failed-mutation atomicity and cache/tenant trust contracts from their specific fixes.
5. Publish tested support tables and actual error/protocol examples. Link security corrections to release notes and migration instructions.
6. Run link/path checks, wheel/scaffold smoke tests and example operation replay. Do not delete compatibility modules or public symbols based on local unused-code searches.

**Acceptance.** Every documented command/path exists, support claims match metadata and verified CI, and examples exercise the implemented contract. Documentation does not make blanket 404/isolation/compatibility guarantees.

**Compatibility/release.** Documentation-only where behavior is unchanged. New extras, dependency consolidations or changed helper defaults are separate additive/breaking changes and require evidence, not this maintenance PR.

**Deployment/rollback.** No production migration; publish alongside the corresponding code release. Revert inaccurate wording if necessary without reverting security controls. Effort 0.5–1 day plus per-PR docs. Risk is accidentally converting a documentation cleanup into a dependency/API redesign.

### Phase 3 release gate

Registry/discovery changes require startup/rebuild regression coverage, introspection comparisons, custom extension survival and representative consumer startup/replay. Missing downstream evidence remains a stated release risk. Documentation commands and installed-package scaffolds must execute in an isolated environment. No apparently unused module is removed without export/dynamic/configuration/downstream-use review.

## Phase 4: behavior or architecture requiring a separate decision

### D-01. Repair the subscription contract as one bounded feature (RD-010)

**Problem/outcome.** Consumer and generator disagree about context and result shape; no channel groups are registered. A context-only patch would be incomplete. Deliver a working, authorized existing subscription protocol after its contract is agreed.

**Scope.** [rail_django/extensions/subscriptions/consumer.py](E:/Projects/libraries/rail-django/rail_django/extensions/subscriptions/consumer.py:84), [rail_django/generators/subscriptions/generator.py](E:/Projects/libraries/rail-django/rail_django/generators/subscriptions/generator.py:234), get_subscription_consumer/schema binding, broadcast/on_commit integration and [rail_django/scaffolding/project_template/root/asgi.py-tpl](E:/Projects/libraries/rail-django/rail_django/scaffolding/project_template/root/asgi.py-tpl:30). Include subscription settings, model metadata, event filters/fields, Channels routing, test fixtures and docs.

**Steps.**

1. Confirm graphql-transport-ws, schema-name routing and current event/field names as the intended public contract. Collect an actual supported client operation.
2. Keep group-registration results outside GraphQL object serialization, or use the already available GraphQL async subscription API if it preserves the chosen interface. Do not add a transport dependency to hide the mismatch.
3. Use a consistent authenticated context for initialization and publication. Correct schema binding and .as_asgi() routes in generated projects.
4. Enforce authenticated model/object/field and tenant authorization on each publication, including revocation while connected. Validate filters/group membership; do not assume subscription-time authorization stays valid.
5. Publish only committed events; handle deletion, rollback, disconnect, duplicate operation IDs, cancelled tasks and group cleanup.
6. Add a local Channels communicator test from generated ASGI route through subscribe → committed mutation → event envelope. Test two users/tenants/schemas, denied filters, no event after rollback and disconnect.
7. Measure active group/task count, bounded event latency and cleanup in a small local workload; verify broker/async ORM behavior for the supported deployment.

**Acceptance.** A real generated subscription registers the expected group, receives exactly the authorized committed event and releases resources on disconnect. Error/protocol envelopes match documented clients. No delivery is enabled before per-event authorization and tenant tests pass.

**Compatibility/release.** Observable fix because clients begin receiving events. Protocol/schema/event redesign is breaking unless proven compatible; put it in D-02 instead of expanding this repair. The audit did not demonstrate an event leak while delivery was broken.

**Deployment/rollback.** Keep optional subscriptions disabled until the full feature gate passes. Canary with isolated local/staging channel layer before production broker rollout. Disable the feature as rollback if delivery/authentication regresses; coordinate reconnect behavior with clients. Effort 3–5 days; maintainer protocol/tenant decisions and local transport provisioning required.

### D-02. Decide support removal or public contract changes explicitly

**Problem/outcome.** Some corrections create a conflict with existing behavior. Resolve those conflicts deliberately rather than claiming all changes are harmless.

**Decision scope.**

- RD-012: ending Django 5.0/5.1 support versus security-patched deployment guidance.
- RD-004: migration from header-only selection to an authorized tenant source.
- RD-007: retained builder/extension lifetime where replacing instances would break callers.
- RD-010: subscription protocol/event changes beyond repairing existing intended behavior.
- Potential scalar/identifier/pagination/error redesigns: no such redesign is justified by this audit.

**Steps/acceptance.** Write a short decision record with affected consumers/contracts, one concrete proposed behavior, migration examples, replay evidence, release numbering/deprecation policy and a safe rollback. Accept security behavior changes explicitly; do not preserve exploitable behavior to satisfy a compatibility slogan. Keep unrelated schema/API redesigns out.

**Tests/release/operations.** Require the same public/import/schema/operation gates as the underlying finding plus supported-version and representative-consumer evidence. If removing an old API is necessary, provide a narrow deprecation/adapter only when a specific consumer need is known. Document whether data migration is actually needed; the audit established none for these policy decisions. Effort depends on decisions and consumer inventory, not a speculative architecture estimate.

### Phase 4 release gate

Subscription delivery remains disabled until real transport, authorization, tenant, transaction and cleanup tests pass. Breaking support/API changes require a maintainer-approved transition and explicit release notes. No major rewrite is a prerequisite for the focused security fixes in Phase 1.

## First five actions

1. **Establish the patched reproducible baseline (B-01/S-01).** Preserve the audited revision and contracts, select a maintained patched Django environment, capture exact skips and clean build/scaffold results. This removes known advisory exposure from the target baseline and makes compatibility comparisons meaningful.
2. **Contain unsafe resolver result caching (S-02 / RD-001).** Disable/bypass paths that can return before authorization, then add collision/revocation regressions. This closes a direct result-disclosure mechanism without waiting for a cache redesign.
3. **Fix reverse-set child authorization (S-03 / RD-002).** Reuse disconnect's policy path and test atomic mixed-child denial. This closes a permission mismatch shared by nested callers.
4. **Remove scope-expanding query fallback (S-04 / RD-003).** Prefer sanitized failure and assert custom/tenant/filter restrictions survive injected database errors. This prevents a recovery path from returning extra rows.
5. **Define and enforce trusted tenant selection (S-05 / RD-004).** Coordinate authorized context/claim/header selection with maintainers and consumers. The current header-only guide can be unsafe despite correct row filtering.

Land the independent release gate B-02 early. S-06–S-08 are small follow-up PRs and should proceed promptly; their position after the five actions does not make CSRF, private-filter access or partial writes acceptable indefinitely.

## Work that can safely wait

Safe cache restoration can wait with unsafe result caching disabled. Broad profiling can wait until authorization and transaction behavior is correct. Subscription repair can wait if the optional feature remains disabled and its current limitation is documented. Extended report/form/table internals and production-scale benchmarking can follow a scoped evidence collection, while their unverified security boundaries remain explicit.

Registry/discovery fixes should be scheduled after urgent reachable security corrections, with interim explicit registration/rebuild procedures where needed. Affected applications should not rely on stale schemas or silent startup behavior.

## Changes to reject on current evidence

- A new generic cache layer, tenant framework or authorization engine: existing helpers cover the demonstrated corrections, and an extra layer does not prove enforcement.
- A key-only RD-001 patch: it leaves cache-hit authorization and revocation unresolved.
- A one-line subscription context patch: it leaves group-list serialization, routing and per-event authorization unverified.
- Broad generator/registry rewrites or merging every settings loader: too much public/hook surface for the verified defects.
- Removing compatibility modules, lazy imports, legacy arguments or “unused” extension points from local searches alone.
- Increasing/removing pagination/property/export limits to claim speed or convenience; no workload justifies it.
- New shared permission/membership caching without correctness, invalidation, revocation and memory bounds.
- Blanket package upgrades, a permanent pin to the first patched Django release, or claiming the local environment is a complete dependency-vulnerability assessment.
- Cosmetic formatting, dependency consolidation and naming cleanup bundled with urgent security changes.
- Automatic repair of previously detached children or partial mutation records without an authorized data investigation.

## Maintainer decisions and remaining evidence

The open decisions are support versions/database matrix, optional versus required database discovery, builder extension lifetime, tenant membership/trusted-source policy, failed-custom-pipeline atomicity and the subscription protocol/event contract. Remote release protections and consumer cache/hook usage also need evidence. These decisions do not block independently verified cache, nested-permission, query-scope, saved-filter and transaction regressions from being prepared.

No consuming application was inspected. Representative downstream operations, custom policy backends, storage/broker behavior and supported-version integration results remain necessary before claiming broader compatibility. The audit and this plan identify specific changes and release gates; they do not establish that the framework is secure, faster or universally backward compatible.
