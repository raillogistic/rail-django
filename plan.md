# Rail Django Review and Refactor Plan

## Goals
- Improve structure and architecture with clear module boundaries and fewer cross-dependencies.
- Raise code quality and consistency with standard patterns, typing, and linting.
- Make the codebase more human-readable by splitting large modules and reducing duplication.
- Add advanced, out-of-the-box features that are safe by default and easy to enable.
- Improve performance with consistent query optimization and observability.
- Strengthen security defaults, enforcement, and auditing.

## Key Review Findings (summary)
- Error handling shadows Django ValidationError, so Django validation errors are not mapped correctly.
- Security middleware passes the wrong AST type to the analyzer, so complexity checks can be skipped.
- Schema always exposes DjangoDebug field, which is risky in production.
- Field masking is skipped for anonymous users, undermining field-level rules.
- Settings override for authentication_required is broken by a casing mismatch.
- Query complexity path in optimize_query references a missing attribute.
- Some modules trigger Django app access at import time (can raise AppRegistryNotReady).
- Several modules show duplication and drift (security settings, performance, rate limiting).

## Phase 0: Baseline, Safety, and Tests
Goals: stabilize behavior and enable safe refactors.
- Add minimal regression tests for:
  - Error mapping (Django ValidationError handling).
  - GraphQL security middleware and complexity limits.
  - Field masking behavior for anonymous vs authenticated users.
  - Schema builder settings overrides (authentication_required).
  - optimize_query with complexity_limit.
- Document current supported Django/Graphene versions in README and docs.
- Set up CI profile (lint + tests) if not already present.
Acceptance criteria:
- Core security and error handling flows covered by tests.
- CI or local test command documented and green.

## Phase 1: Correctness and Security Fixes
Goals: fix correctness/security regressions before structural changes.
- Fix ValidationError naming collision in error handling and update tests.
- Fix GraphQL security middleware to pass the correct document node for analysis.
- Gate DjangoDebug exposure by DEBUG and schema settings (disable by default in prod).
- Enforce field masking for anonymous users or explicitly deny access with clear errors.
- Fix authentication_required override casing mismatch in schema registry.
- Fix optimize_query complexity path to use the correct analyzer API.
- Remove import-time get_user_model usage in core/security; make it lazy.
Acceptance criteria:
- All fixes covered by tests and verified in sample schema build.
- No security bypass when DEBUG is False.

## Phase 2: Architecture and Structure
Goals: reduce duplication and clarify boundaries.
- Consolidate configuration:
  - Single settings source of truth (defaults + config_proxy + schema overrides).
  - Merge SecuritySettings and PerformanceSettings into one shared config model.
- Unify security and performance services:
  - One rate limiter implementation (remove duplicate RateLimiter classes).
  - One query complexity analyzer (security vs performance).
- Establish module boundaries:
  - core/: schema build, registry, settings, errors.
  - generators/: type/query/mutation builders only.
  - security/: auth, rbac, field permissions, input validation, audit.
  - extensions/: optional add-ons with clean integration points.
- Introduce explicit service interfaces or dependency injection for:
  - AuditLogger, RateLimiter, QueryOptimizer.
Acceptance criteria:
- Clear dependency graph (core does not import extensions by default).
- Single path for settings and rate limiting.

## Phase 3: Code Quality and Readability
Goals: simplify code paths and make the library easier to maintain.
- Split large files:
  - generators/mutations.py -> crud.py, bulk.py, method_mutations.py, errors.py.
  - generators/queries.py -> list_queries.py, pagination.py, grouping.py, filters.py.
  - generators/types.py -> object_types.py, input_types.py, enums.py, dataloaders.py.
- Remove duplication:
  - Repeated graphql_meta assignments.
  - Duplicate branches and dead code.
- Standardize naming and error handling conventions.
- Add targeted comments only where logic is complex.
- Introduce linting (ruff/flake8) and formatting (black) configuration.
Acceptance criteria:
- Reduced module sizes and lower cognitive load for core flows.
- Lint and format checks pass with minimal warnings.

## Phase 4: Performance Enhancements
Goals: predictable query performance and lower query count.
- Consolidate query optimizer:
  - Use GraphQL AST selection analysis in one place.
  - Make select_related/prefetch_related decisions consistent.
- Improve ordering for computed properties:
  - Warn or cap results at lower limits.
  - Provide explicit config for property ordering.
- Add optional query caching hooks (opt-in) with safe invalidation patterns.
- Add query metrics (query count, duration, N+1 detection).
Acceptance criteria:
- Demonstrable reduction in query count for list and nested queries.
- Metrics available for tracing slow queries.

## Phase 5: Security Hardening
Goals: secure defaults, explicit overrides, and auditability.
- Enforce access guards in a single middleware layer.
- Introspection and GraphiQL defaults:
  - Disabled in production unless explicitly enabled.
  - Role-based allowlist for introspection.
- JWT hardening:
  - Rotation support, refresh token reuse detection.
  - Configurable cookie policies (SameSite, Secure, domain).
- Input validation defaults:
  - Consistent rules and severity thresholds per schema.
- Improve audit logging:
  - PII-safe redaction, structured event storage, retention policy hooks.
Acceptance criteria:
- Security defaults are strict and require opt-in to loosen.
- Clear security config guide and documented threat model.

## Phase 6: Advanced and Out-of-the-Box Features
Goals: extend capabilities without cluttering the core.
- Persisted queries / allowlisting (APQ).
- Schema registry enhancements:
  - Version diffing, change log, export endpoint.
- OpenTelemetry/Sentry integration hooks.
- Optional GraphQL subscriptions (Django Channels).
- Plugin system:
  - Pre/post schema build hooks.
  - Query/mutation interception hooks.
Acceptance criteria:
- Features are opt-in and documented with minimal setup.

## Phase 7: Documentation and Migration
Goals: guide users through changes safely.
- Update docs and examples to match new config and defaults.
- Add a migration guide with deprecations and replacement settings.
- Provide sample project templates updated with new structure.
Acceptance criteria:
- Docs are aligned with behavior and tests validate examples.

## Sequencing (suggested)
1. Phase 0 + Phase 1 in one iteration to stabilize behavior.
2. Phase 2 and Phase 3 together for refactor and cleanup.
3. Phase 4 and Phase 5 for performance and security.
4. Phase 6 and Phase 7 for enhancements and documentation.
