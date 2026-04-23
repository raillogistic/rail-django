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
**Status:** TODO
**Goal:** Review hot paths, repeated work, startup overhead, blocking I/O, algorithmic complexity, concurrency limits, and scaling risks.
**Tasks:**
- [ ] Identify hot paths
- [ ] Review repeated scans/lookups
- [ ] Review startup/import overhead
- [ ] Review blocking I/O
- [ ] Review concurrency/contention risks
- [ ] Identify first scaling failure points
**Completion notes:**
-

### Phase 5 — Performance Review
**Status:** TODO
**Goal:** Review CPU cost, memory usage, caching, async correctness, serialization overhead, and unnecessary abstractions.
**Tasks:**
- [ ] Review CPU-heavy paths
- [ ] Review memory lifecycle and retention
- [ ] Review cache opportunities and risks
- [ ] Check async/sync correctness
- [ ] Review serialization/deserialization overhead
- [ ] Identify concrete optimizations
**Completion notes:**
-

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

**Current phase:** Phase 4 - Bottlenecks and Scalability

**Current status:** TODO

**Current task:** Review hot paths, startup overhead, repeated work, and
blocking I/O in the framework's runtime and extension surfaces.

**Next action:** Trace startup-heavy imports, repeated registry scans, and
blocking filesystem or database work in request and job execution paths.

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
- None yet.

### Performance
- None yet.

### Reliability
- None yet.

---

## 7. Open Questions / Blockers

- The standard pytest path is currently blocked by an unrelated Django-version
  mismatch in `tests.models`: `django.db.models.GeneratedField` is unavailable
  in the active Django 3.2 environment.

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
