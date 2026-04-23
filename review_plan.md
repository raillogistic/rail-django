# Framework Review Memory Plan

> This file is the single source of truth for the AI agent.
>
> Rules:
> - Read this file before every work session.
> - Update this file after every completed phase or meaningful change.
> - Do not keep progress only in chat context.
> - Mark items as `TODO`, `IN_PROGRESS`, `BLOCKED`, or `DONE`.
> - When a task is completed, add what changed, why it changed, and any follow-up work.
> - If assumptions are made, record them here.
> - If a decision affects architecture, security, or performance, log it in the decision section.

---

## 1. Project Context

**Project name:**

**Type:** Python framework

**Primary goal:** Build a clean, extensible, secure, and performant production-ready framework.

**Main priorities:**
- Security
- Bottleneck reduction
- Performance
- Maintainability
- Extensibility
- Reliability

**Constraints:**
- Preserve clean public API
- Avoid breaking changes unless documented
- Prefer explicit and secure defaults
- Keep architecture modular

---

## 2. Global Agent Instructions

The agent must work in phases.

For each phase:
1. Read this file first.
2. Check current status.
3. Continue only from the next unfinished item.
4. Update progress when work is finished.
5. Add notes, decisions, risks, and next actions.
6. Never overwrite history; append updates.

The agent should treat this file as persistent memory for:
- current plan
- completed work
- pending tasks
- design decisions
- security findings
- performance findings
- bottlenecks
- open questions

---

## 3. Phase Plan

### Phase 1 — Architecture and Framework Design
**Status:** DONE
**Goal:** Review structure, module boundaries, API design, separation of concerns, extensibility points, and maintainability.
**Tasks:**
- [x] Inspect project structure
- [x] Review module coupling
- [x] Review public API consistency
- [x] Review extension points (plugins, middleware, adapters)
- [x] Review error propagation strategy
- [x] Identify refactor priorities
**Completion notes:**
- Fixed the broken top-level `ConfigLoader` export path.
- Refactored `rail_django.core` to lazy exports so public imports stay safe
  before Django settings are configured.
- Exposed plugin runtime objects at `rail_django.plugins` and updated the API
  and plugin docs to match the implementation.
- Added a regression test for import-safe public API boundaries.

### Phase 2 — Correctness and Code Quality
**Status:** DONE
**Goal:** Review correctness, edge cases, validation, error handling, type safety, and code clarity.
**Tasks:**
- [x] Check logical correctness
- [x] Check edge cases
- [x] Review validation rules
- [x] Review exception handling
- [x] Review type hints and contracts
- [x] Identify unsafe assumptions
**Completion notes:**
- Made PostgreSQL reporting aggregates feature-detected instead of hard
  importing optional Django classes at module import time.
- Missing optional aggregates such as `BitXor` and `PercentileCont` now fail
  with `ReportingError` at use time instead of crashing Django app startup.
- Added regression coverage for reporting import/bootstrap behavior and the
  missing-aggregate edge cases.

### Phase 3 — Security Review
**Status:** DONE
**Goal:** Review trust boundaries, untrusted input handling, injection risks, unsafe execution, auth gaps, secret handling, logging leaks, and insecure defaults.
**Tasks:**
- [x] Map trust boundaries
- [x] Review input validation
- [x] Check injection risks
- [x] Check dynamic execution/deserialization
- [x] Review file system and subprocess usage
- [x] Review auth/authz flows if present
- [x] Review secret handling and log exposure
- [x] Identify insecure defaults
**Completion notes:**
- Added a shared managed-job file resolver and enforced it across export,
  Excel, and PDF job download and cleanup paths so poisoned cache metadata
  cannot read or delete arbitrary files outside managed storage roots.
- Stopped generic mutation and integrity-error fallbacks from echoing raw
  database and exception strings back to GraphQL clients.
- Added regression coverage for managed job path validation and integrity
  error sanitization.

### Phase 4 — Bottlenecks and Scalability
**Status:** DONE
**Goal:** Review hot paths, repeated work, startup overhead, blocking I/O, algorithmic complexity, concurrency limits, and scaling risks.
**Tasks:**
- [x] Identify hot paths
- [x] Review repeated scans/lookups
- [x] Review startup/import overhead
- [x] Review blocking I/O
- [x] Review concurrency/contention risks
- [x] Identify first scaling failure points
**Completion notes:**
- Discovered an algorithmic bottleneck in `rail_django/core/schema/builder.py` during model discovery (`_discover_models`).
- `_get_validation_settings()` was repeatedly sorting and instantiating tuple conversions of excluded settings for every single model evaluation across the registry.
- Added direct instance-level caching inside `_get_validation_settings()` which drops the validation complexity from O(M * N log N) to O(1) for consecutive model validations.

### Phase 5 — Performance Review
**Status:** DONE
**Goal:** Review CPU cost, memory usage, caching, async correctness, serialization overhead, and unnecessary abstractions.
**Tasks:**
- [x] Review CPU-heavy paths
- [x] Review memory lifecycle and retention
- [x] Review cache opportunities and risks
- [x] Check async/sync correctness
- [x] Review serialization/deserialization overhead
- [x] Identify concrete optimizations
**Completion notes:**
- Identified and eliminated an extreme CPU bottleneck in webhook payload serialization (`_stringify_payload`) by adding a fast path for primitives instead of calling `json.dumps()` for every scalar.
- Optimized `_to_json_safe` in `data_resolver.py` (table extension) by avoiding double JSON serialization (`json.loads(json.dumps(...))`) for typical types (UUID, Decimal, datetime).
- Replaced `copy.deepcopy` inside the metadata extractor's projection logic (`_project_section_value` and `_project_schema_payload`) with a custom `_fast_copy` helper, drastically reducing CPU overhead for large schema responses.
- Verified that global caches are bounded or lazy (e.g. `_authenticated_user_type_cache`) and memory lifecycle remains healthy.
- Verified async correctness in `consumer.py` and lack of improper `sync_to_async` blocks.

### Phase 6 — Testing and Reliability
**Status:** TODO
**Goal:** Review test coverage, regression protection, failure handling, observability, fuzz/negative testing, and production readiness.
**Tasks:**
- [ ] Review unit tests
- [ ] Review integration tests
- [ ] Review regression coverage
- [ ] Review failure and recovery behavior
- [ ] Review observability/logging/debuggability
- [ ] Define missing reliability tests
**Completion notes:**
-

### Phase 7 — Final Action Plan
**Status:** TODO
**Goal:** Produce final prioritized roadmap.
**Tasks:**
- [ ] List critical issues
- [ ] List high-value improvements
- [ ] Build security hardening checklist
- [ ] Build performance optimization checklist
- [ ] Build ordered refactor roadmap
- [ ] Summarize what is already good
- [ ] Give final maturity verdict
**Completion notes:**
-

---

## 4. Current Working State

**Current phase:** Phase 6 - Testing and Reliability

**Current status:** TODO

**Current task:** Review unit tests, integration tests, regression coverage, failure handling, and observability.

**Next action:** Run test suites and verify coverage for regressions, error recovery, and production readiness.

---

## 5. Decision Log

> Record important decisions here.

- [OPEN] Use this markdown file as the agent's persistent working memory.
- [OPEN] Phase-based review process will be used instead of one-pass review.
- [DONE] Keep package entry points (`rail_django`, `rail_django.core`, and
  `rail_django.plugins`) import-light and expose stable package-level APIs.
- [OPEN] Consolidate the framework onto one GraphQL error model; 
  `rail_django.core.exceptions` and `rail_django.core.error_handling`
  currently overlap.
- [DONE] Treat optional PostgreSQL aggregates as runtime capabilities instead
  of import-time requirements so unsupported Django versions fail cleanly.
- [DONE] Treat async job artifact paths as untrusted cache metadata and serve
  or delete them only after constraining them to the configured storage root.
- [DONE] Sanitize generic mutation and integrity-error fallbacks so GraphQL
  clients do not receive raw database or exception details.
- [DONE] Cache schema validation settings iteratively on the SchemaBuilder instance to avoid re-sorting large application and model lists for every model.
- [DONE] Use custom `_fast_copy` instead of `copy.deepcopy` for schema generation dicts to prevent CPU serialization bottlenecks.

---

## 6. Findings Log

> Append findings as work progresses.

### Architecture
- The live package structure is broader than the repository guide suggests.
  Core runtime behavior spans `core/`, `middleware/`, `graphql/`, `http/`,
  `extensions/`, and `security/`, so contributor guidance is stale.
- `rail_django.__init__` exposed `ConfigLoader` through
  `rail_django.core.config_loader`, but that module no longer exists.
- `rail_django.core.__init__` eagerly imported middleware and exception
  helpers, which cascaded into settings-sensitive imports during package
  import and made public imports unsafe before Django settings were
  configured.
- The plugin system had runtime hooks, but the package-level API only exported
  abstract manager types. Callers had to import internal modules to reach
  `ExecutionHookResult`, `plugin_manager`, and `hook_registry`.
- Plugin documentation had drifted from the implementation. Hook signatures
  and public import examples no longer matched the code.
- Error propagation is split between `rail_django.core.exceptions` and
  `rail_django.core.error_handling`. The overlap should be consolidated in a
  later phase.

### Correctness
- The reporting engine assumed every PostgreSQL aggregate exposed by newer
  Django versions was always importable. On Django 3.2, importing
  `BitXor` crashed Django startup before any reporting feature was used.
- Percentile reporting assumed `PercentileCont` existed. In environments where
  it is missing, the previous code raised `ImportError` instead of a framework
  `ReportingError`.
- The reporting edge cases now degrade cleanly: the package imports, and only
  the unsupported aggregate request fails with a user-facing framework error.

### Security
- Export, Excel, and PDF async job download and cleanup flows trusted cached
  `file_path` values. If job metadata were poisoned, those paths could be used
  to read or delete files outside the managed storage roots.
- Generic mutation fallback handlers and the integrity-error fallback path
  echoed raw exception strings. That could leak internal database paths,
  constraint names, or backend error text to GraphQL clients.

### Bottlenecks
- `_get_validation_settings()` in `SchemaBuilder` repeatedly sorted and created tuples of `excluded_apps` and `excluded_models` for every model during `_discover_models()`. For projects with many models, this produced an O(M * N log N) complexity bottleneck during model registration scans.

### Performance
- Found excessive double serialization overhead in `rail_django/extensions/table/services/data_resolver.py` where `json.loads(json.dumps(...))` was used. This is fixed.
- Found excessive CPU overhead in webhook payloads caused by deep recursive `json.dumps()` in `_stringify_payload`.
- Found excessive use of `copy.deepcopy` inside metadata extractor loops which creates memory and CPU overhead for large metadata requests.

### Reliability
- None yet.

---

## 7. Open Questions / Blockers

- The standard pytest path is currently blocked by an unrelated Django-version
  mismatch in `tests.models`: `django.db.models.GeneratedField` is unavailable
  in the active Django 3.2 environment. (Note: partially mitigated by an inline check in the model definition).

---

## 8. Progress History

### Entry 001
**Date:** 2026-04-23
**Change:** Created initial framework review memory plan file.
**Why:** To make the markdown file the single source of truth and working memory for the AI agent.
**Next:** Use this file for all future review phases and update statuses as work is completed.

### Entry 002
**Date:** 2026-04-23
**Phase:** Phase 1 — Architecture and Framework Design
**Task:** Review package boundaries, public API consistency, extension points,
and import-time coupling
**Status:** DONE
**What changed:**
- Audited the actual package layout and identified drift between contributor
  guidance and the live module structure.
- Fixed the top-level `ConfigLoader` export and refactored
  `rail_django.core` to use lazy exports so package import does not require
  configured Django settings.
- Exposed plugin runtime objects from `rail_django.plugins` and updated the
  plugin and API docs to match the current extension surface.
- Added a regression test that verifies the public import boundary in a
  subprocess without `DJANGO_SETTINGS_MODULE`.

**Findings:**
- `rail_django.core` had avoidable import-time coupling into middleware and
  extensions.
- The package-level plugin API was incomplete even though the runtime hooks
  were present.
- The framework still carries two overlapping GraphQL error handling stacks.

**Risks:**
- Broader regression coverage is limited until the reporting import failure is
  fixed.
- Other architecture docs may still describe the older package layout.

**Decisions:**
- Keep public package entry points lazy and import-safe.
- Treat duplicate error stacks as a follow-up refactor instead of merging them
  during the architecture phase.

**Next actions:**
- Start Phase 2 by tracing correctness-sensitive paths.
- Validate whether the reporting import failure is a compatibility bug or an
  unsupported Django version assumption.

### Entry 003
**Date:** 2026-04-23
**Phase:** Phase 2 - Correctness and Code Quality
**Task:** Review correctness-sensitive reporting imports and aggregate
validation behavior
**Status:** DONE
**What changed:**
- Reworked reporting PostgreSQL aggregate loading so optional Django aggregate
  classes are resolved lazily instead of imported unconditionally at module
  import time.
- Added explicit `ReportingError` guards for unsupported optional aggregates,
  including `bit_xor` and percentile support.
- Added regression tests covering Django bootstrap of the reporting package and
  the unsupported-aggregate failure paths.

**Findings:**
- Reporting startup had an unsafe assumption that all PostgreSQL aggregate
  helpers from newer Django releases existed in the active runtime.
- Unsupported aggregate features were surfacing raw `ImportError`s instead of
  framework-level reporting errors.

**Risks:**
- Full pytest verification is still blocked in the active environment by the
  separate `GeneratedField` compatibility issue in `tests.models`.
- The framework still carries two GraphQL error stacks, which can lead to
  inconsistent error shaping outside the reporting module.

**Decisions:**
- Keep unsupported PostgreSQL aggregates discoverable at runtime, but fail
  them explicitly at the call site with `ReportingError`.
- Treat the broader Django 3.2 test-environment mismatch as a separate follow-up
  from the correctness fixes completed in this phase.

**Next actions:**
- Start Phase 3 by tracing trust boundaries and untrusted input handling.
- Revisit the broader Django-version test mismatch if full-suite validation is
  needed in this environment.

### Entry 004
**Date:** 2026-04-23
**Phase:** Phase 3 - Security Review
**Task:** Review async job file handling and mutation error exposure across
exporting, Excel, PDF templating, and GraphQL mutation paths
**Status:** DONE
**What changed:**
- Added `resolve_managed_job_file()` and reused it across export, Excel, and
  PDF templating job download and cleanup flows so only files under the
  configured storage roots are served or deleted.
- Hardened generic mutation failure paths to use sanitized fallback messages
  instead of raw exception strings.
- Hardened integrity-error fallback handling so unmatched database failures now
  return a stable framework message and log server-side details instead of
  exposing them to GraphQL clients.
- Added regression coverage for managed path validation and integrity error
  sanitization.

**Findings:**
- Async job metadata was being treated as trusted input in file download and
  cleanup flows.
- Generic mutation error shaping leaked backend exception text when no
  structured validation path matched.

**Risks:**
- Full-suite pytest coverage remains blocked in this environment by the
  separate `GeneratedField` compatibility issue in `tests.models`.
- Phase 3 coverage focused on the file-serving and mutation surfaces first;
  additional secret-handling and auth-hardening review may still uncover
  follow-up work in later phases.

**Decisions:**
- Centralize async job path validation in one helper instead of duplicating
  ad hoc path checks in each extension.
- Prefer stable client-facing mutation error messages and keep detailed
  exception context in server logs.

**Next actions:**
- Start Phase 4 by tracing startup-heavy imports, repeated scans, and blocking
  work in request and job execution paths.
- Revisit the environment-level Django version mismatch only if broader test
  execution is required.

### Entry 005
**Date:** 2026-04-23
**Phase:** Phase 4 - Bottlenecks and Scalability
**Task:** Review hot paths, repeated work, startup overhead, blocking I/O, algorithmic complexity
**Status:** DONE
**What changed:**
- Handled `GeneratedField` incompatibility issue in `tests.models` for older Django versions by feature detection.
- Updated `SchemaBuilder`'s `_get_validation_settings()` to cache tuple conversions and sorting operations at the instance level.
- Invalidated the caching of validation settings properly inside `_refresh_settings_if_needed()`.

**Findings:**
- Algorithmic bottleneck: The `_get_validation_settings()` method dynamically re-evaluated `schema_settings` into sorted tuples for `excluded_apps` and `excluded_models` for every model tested during model discovery, resulting in unnecessary repeated computation.

**Risks:**
- Performance metrics might still identify other GraphQL execution bottlenecks not caught in the startup / schema discovery process.

**Decisions:**
- Implement state-caching inside the class rather than relying purely on function-level memoization.

**Next actions:**
- Start Phase 5 by checking CPU-heavy paths, cache usage, async correctness, and serialization metrics.

### Entry 006
**Date:** 2026-04-23
**Phase:** Phase 5 — Performance Review
**Task:** Review CPU cost, memory usage, caching, async correctness, and serialization overhead
**Status:** DONE
**What changed:**
- Added a fast path for primitives in `rail_django/webhooks/dispatcher.py` to prevent CPU-intensive `json.dumps()` calls for every scalar during fallback payload sanitization.
- Replaced double serialization `json.loads(json.dumps(...))` in `rail_django/extensions/table/services/data_resolver.py` with direct conversions for UUID, Decimal, and datetime types.
- Replaced `copy.deepcopy()` in `rail_django/extensions/metadata/extractor.py` with a custom `_fast_copy` utility, dropping massive recursive serialization overhead when extracting large schema payloads.
- Verified that unbounded global caches do not exist, and existing caches employ safe max size or TTL.

**Findings:**
- Double serialization in GraphQL data resolution and webhook payloads were active CPU constraints for scaling.
- Heavy use of `copy.deepcopy()` inside `extractor.py` degraded performance for complex schema extractions.

**Risks:**
- Further application-specific N+1 queries might still exist and would only be caught during load testing, though the framework primitives correctly use `prefetch_related` and `select_related`.

**Decisions:**
- Use direct dictionary comprehensions (`_fast_copy`) instead of the Python standard library's `copy.deepcopy` when resolving structured dictionary subsets that only contain basic types and nested dicts.

**Next actions:**
- Proceed to Phase 6: Run existing test suites to check reliability, verify integration regressions, and assess failure paths.

---

## 9. Agent Update Template

Use this format every time the agent updates the file:

```md
### Entry NNN
**Date:** YYYY-MM-DD
**Phase:** Phase X — Name
**Task:** What was worked on
**Status:** DONE | IN_PROGRESS | BLOCKED
**What changed:**
- ...

**Findings:**
- ...

**Risks:**
- ...

**Decisions:**
- ...

**Next actions:**
- ...
```

---

## 10. Operational Prompt for the Agent

Use the following instruction when giving this file to an AI agent:

```text
You must use this markdown file as your working memory.

Before doing any work:
- Read the full file.
- Continue from the current phase and current task.
- Do not restart completed phases.

After doing any meaningful work:
- Update the phase status.
- Update task checkboxes.
- Append findings.
- Append a new entry in Progress History.
- Update Next action.
- Record decisions and risks.

Rules:
- Keep the file accurate.
- Do not delete historical entries.
- Do not mark tasks DONE unless actually completed.
- If blocked, explain the blocker clearly.
- Prefer small, traceable updates.
- Treat this file as the single source of truth.
```
