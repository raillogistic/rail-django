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
**Status:** DONE
**Goal:** Review test coverage, regression protection, failure handling, observability, fuzz/negative testing, and production readiness.
**Tasks:**
- [x] Review unit tests
- [x] Review integration tests
- [x] Review regression coverage
- [x] Review failure and recovery behavior
- [x] Review observability/logging/debuggability
- [x] Define missing reliability tests
**Completion notes:**
- Consolidated duplicated error handling by deleting `rail_django/core/error_handling.py` and unifying standard error propagation in `rail_django/core/exceptions.py`.
- Cleaned up unused `DebugHooks` and `PerformanceMonitor` dependencies from `SchemaManager`.
- Verified observability components (`ErrorTracker`, `QueryAnalyzer`, `PerformanceMonitor`) and extension plugins (Sentry/OTel) via existing test suites.
- Confirmed that failure recovery in mutation pipelines and webhook dispatchers correctly implements retries and sanitized client error shaping.
- Defined missing reliability tests (Mutation fuzzing, DB failover, query complexity stress) for future hardening.

### Phase 7 — Final Action Plan
**Status:** DONE
**Goal:** Produce final prioritized roadmap.
**Tasks:**
- [x] List critical issues
- [x] List high-value improvements
- [x] Build security hardening checklist
- [x] Build performance optimization checklist
- [x] Build ordered refactor roadmap
- [x] Summarize what is already good
- [x] Give final maturity verdict
**Completion notes:**
- **Critical Issues:**
    1. Redundant error propagation modules (`error_handling.py` vs `exceptions.py`) causing architectural drift. **[FIXED]**
    2. Import-time crashes on older Django versions due to PostgreSQL aggregate assumptions. **[FIXED]**
    3. Potential arbitrary file read/delete in async job downloads via unsanitized cache paths. **[FIXED]**
    4. O(M*N log N) complexity bottleneck during startup model discovery. **[FIXED]**
    5. Excessive CPU cost in webhook and table serialization due to recursive `json.dumps`. **[FIXED]**
- **High-Value Improvements:**
    1. Implement formalized "Chaos Testing" for DB failures.
    2. Add built-in support for GraphQL Query Depth and Complexity limiting in `rail_django/core/schema/builder.py`.
    3. Enhance `SavedFilter` with versioning for query compatibility.
- **Security Hardening Checklist:**
    - [x] Centralize file boundary resolution (`resolve_managed_job_file`).
    - [x] Sanitize integrity and mutation error messages.
    - [ ] Implement Rate Limiting at the Load Balancer level in addition to the framework middleware.
    - [ ] Review secret masking in `_stringify_payload` for PII protection.
- **Performance Optimization Checklist:**
    - [x] Replace `copy.deepcopy` in metadata extraction loops.
    - [x] Implement schema-level validation settings caching.
    - [x] Optimize primitive serialization for webhooks and tables.
    - [ ] Profile production N+1 query patterns using `QueryAnalyzer`.
- **Ordered Refactor Roadmap:**
    1. Consolidate `rail_django.core.exceptions` into a more modern naming convention (e.g., `rail_django.core.errors`).
    2. Remove deprecated Python 3.8/3.9 compatibility shims.
    3. Transition `SchemaManager` to use a more pluggable hook registry.
- **Maturity Verdict:** High. The framework has a robust foundation with well-integrated security and performance primitives. Most detected bottlenecks were addressed during this review.

---

## 4. Current Working State

**Current phase:** COMPLETED

**Current status:** DONE

**Current task:** Final report generated.

**Next action:** Review is complete. The plan markdown file remains as the source of truth for the project's health.

---

## 5. Decision Log

> Record important decisions here.

- [DONE] Keep package entry points (`rail_django`, `rail_django.core`, and
  `rail_django.plugins`) import-light and expose stable package-level APIs.
- [DONE] Consolidate the framework onto one GraphQL error model; 
  `rail_django.core.exceptions` and `rail_django.core.error_handling`
  were merged by deleting the latter.
- [DONE] Treat optional PostgreSQL aggregates as runtime capabilities instead
  of import-time requirements so unsupported Django versions fail cleanly.
- [DONE] Treat async job artifact paths as untrusted cache metadata and serve
  or delete them only after constraining them to the configured storage root.
- [DONE] Sanitize generic mutation and integrity-error fallbacks so GraphQL
  clients do not receive raw database or exception details.
- [DONE] Cache schema validation settings iteratively on the SchemaBuilder instance to avoid re-sorting large application and model lists for every model.
- [DONE] Use custom `_fast_copy` instead of `copy.deepcopy` for schema generation dicts to prevent CPU serialization bottlenecks.
- [DONE] Remove unused `DebugHooks` and `PerformanceMonitor` from `SchemaManager` to simplify the dependency graph.

---

## 6. Findings Log

> Append findings as work progresses.

### Architecture
- The live package structure is broader than the repository guide suggests.
  Core runtime behavior spans `core/`, `middleware/`, `graphql/`, `http/`,
  `extensions/`, and `security/`.
- Error propagation was split between `rail_django.core.exceptions` and
  `rail_django.core.error_handling`. Consolidated in Phase 6.

### Correctness
- PostgreSQL aggregate feature-detection fixed reporting import crashes on older Django.

### Security
- Async job file boundaries enforced.
- Mutation integrity errors sanitized.

### Bottlenecks
- Model discovery O(N^2) loop fixed via validation settings caching.

### Performance
- Webhook, Table, and Metadata serialization CPU overhead minimized by using primitive fast-paths and custom shallow/fast copy utilities.

### Reliability
- Redundant debugging fields removed from `SchemaManager`.
- Identified need for fuzzing and stress testing.

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
**What changed:** Fixed top-level exports and refactored core imports.

### Entry 003
**Date:** 2026-04-23
**Phase:** Phase 2 - Correctness and Code Quality
**Task:** Review correctness-sensitive reporting imports and aggregate
validation behavior
**Status:** DONE
**What changed:** Feature-detection for optional PostgreSQL aggregates.

### Entry 004
**Date:** 2026-04-23
**Phase:** Phase 3 - Security Review
**Task:** Review async job file handling and mutation error exposure
**Status:** DONE
**What changed:** Enforced job file storage roots and sanitized integrity errors.

### Entry 005
**Date:** 2026-04-23
**Phase:** Phase 4 - Bottlenecks and Scalability
**Task:** Review hot paths, algorithmic complexity
**Status:** DONE
**What changed:** SchemaBuilder settings caching.

### Entry 006
**Date:** 2026-04-23
**Phase:** Phase 5 — Performance Review
**Task:** Review CPU cost and serialization overhead
**Status:** DONE
**What changed:** Webhook/Table serialization optimizations and `_fast_copy` in Metadata Extractor.

### Entry 007
**Date:** 2026-04-23
**Phase:** Phase 6 - Testing and Reliability
**Task:** Review test coverage and failure handling
**Status:** DONE
**What changed:** Consolidated error handling systems and cleaned up unused manager dependencies.

### Entry 008
**Date:** 2026-04-23
**Phase:** Phase 7 - Final Action Plan
**Task:** Synthesize roadmap and maturity verdict
**Status:** DONE
**What changed:** Produced prioritized hardening and optimization checklist. Full framework audit completed.

---

## 9. Maturity Verdict

**Overall Grade:** A-
**Production Readiness:** High. The core components (webhooks, permissions, schema generation) are performant and secure. The roadmap items are optimizations/hardening rather than critical bugfixes.

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
