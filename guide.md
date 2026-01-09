# Rail Django Deep Scan Report

## Scope
- Scanned GraphQL views, schema builder, middleware, performance, and security modules.
- Reviewed REST endpoints for schema management, export, templating, and health checks.
- Checked settings/config plumbing and defaults for runtime behavior.

## High Priority Findings
- **GraphQL middleware not wired to execution path.** Security/perf middleware (rate limiting, validation, complexity checks) are created but never passed to GraphQL execution. `rail_django/core/schema.py` stores middleware but `rail_django/views/graphql_views.py` and `rail_django/urls.py` never apply it. This makes many security/perf features effectively no-ops.
- **Schema management API is unauthenticated.** `rail_django/api/views.py` exposes schema create/update/delete and discovery without auth checks; `rail_django/api/urls.py` exposes them publicly.
- **JWT refresh tokens can be used as access tokens.** `rail_django/extensions/auth.py` does not enforce token type in `verify_token`, while `MultiSchemaGraphQLView._validate_token` accepts any valid token with `user_id`. Refresh tokens can be used to access protected endpoints.
- **Export endpoint can exfiltrate data.** `rail_django/extensions/exporting.py` allows any authenticated user to export arbitrary models/fields with no per-model/field permission checks or row limits.
- **Settings key mismatch disables controls.** The code expects `performance_settings`, `security_settings`, and `type_generation_settings`, but `settings.py` example uses `PERFORMANCE`, `SECURITY`, and `TYPE_SETTINGS`. This makes intended controls ineffective.

## Performance Recommendations (Endpoint Speed and Throughput)
1. **Wire GraphQL middleware into execution.**
   - Ensure `GraphQLView` receives the middleware stack (rate limiting, validation, complexity, logging, perf).
   - Suggested location: set `self.middleware` in `MultiSchemaGraphQLView.dispatch` using `schema_registry.get_schema_builder(schema).get_middleware()` or a unified stack from `rail_django/core/middleware.py`.

2. **Fix and consolidate query optimization paths.**
   - There are two optimizers (`rail_django/core/performance.py` and `rail_django/extensions/optimization.py`). Consolidate into one and ensure it uses GraphQL selection sets to avoid over-prefetching.
   - Current `core/performance.py` selects all relations; this can explode query cost on wide models.

3. **Use dataloaders for N+1, not blanket prefetch.**
   - Dataloader batching per field is more precise than prefetching every relation.
   - Consider `graphene-django-optimizer` or a local dataloader for FK/M2M.

4. **Avoid per-request schema rebuild checks.**
   - `MultiSchemaGraphQLView` maintains a per-instance cache; in Django CBVs this does not persist across requests.
   - Use a shared cache keyed by schema + version in the registry or builder.

5. **Export endpoint should stream and cap.**
   - Add max row limits and streaming (chunked CSV).
   - Use select_related/prefetch for export fields and a whitelist for allowed fields.

6. **Reduce costly operations in resolvers.**
   - In grouping queries, each FK label triggers a query (`rail_django/generators/queries.py`). Use `values()` with joins or prefetch map.
   - For property ordering, converting to list and sorting loads full result sets; apply a server-side cap or require explicit limit.

7. **Performance monitoring should be low overhead in prod.**
   - `tracemalloc` and `connection.queries` are expensive and/or disabled in production. Guard by settings and avoid always-on tracing.

## Security Gaps and Recommendations
1. **Protect schema management endpoints.**
   - Require JWT + admin permissions for create/update/delete/disable operations in `rail_django/api/views.py`.
   - Add rate limiting to management endpoints.

2. **Disable GraphiQL/Playground and introspection in prod.**
   - Default settings allow introspection and GraphiQL. Enforce environment-based defaults in `rail_django/defaults.py` and ensure they are actually applied.
   - Serve playground assets locally or pin to SRI if kept.

3. **Enforce token type for JWT.**
   - Reject refresh tokens for access; include `type` in `verify_token` and validate in `authenticate_request` and `MultiSchemaGraphQLView._validate_token`.
   - Consider `jti` + blacklist or rotation for refresh tokens.

4. **CSRF and cookie auth alignment.**
   - `csrf_exempt` is used on GraphQL and REST views. If JWTs are in cookies, require CSRF or enforce header-only tokens.

5. **Rate limiting must be real and shared.**
   - Current rate limiting is in-memory per process (`rail_django/security/graphql_security.py`, `rail_django/middleware/auth_middleware.py`).
   - Move limits to Django cache or Redis and apply globally to GraphQL and REST endpoints.

6. **Export and templating endpoints need authorization.**
   - Enforce per-model/field permissions and a whitelist for export fields.
   - Ensure template endpoints require auth and validate guard permissions.

7. **Sensitive headers and CORS.**
   - `CORS_ALLOW_ALL_ORIGINS = True` in settings and `Access-Control-Allow-Origin: *` in REST views. Lock down allowed origins in prod.

## Refactor / Code Health Recommendations
1. **Fix broken or conflicting modules.**
   - `rail_django/extensions/optimization.py` has a syntax-level indentation bug in `_get_prefetch_related_fields`.
   - `rail_django/core/middleware.py` references a removed `CachingMiddleware`.
   - `rail_django/extensions/media.py` duplicates performance middleware instead of media handling.

2. **Unify middleware implementations.**
   - There are two `GraphQLPerformanceMiddleware` classes with different behavior in `rail_django/middleware/performance.py` and `rail_django/middleware/performance_middleware.py`. Pick one canonical path.

3. **Settings schema consistency.**
   - Align keys across defaults, config proxy, and docs. Prefer one naming scheme:
     - `schema_settings`, `query_settings`, `mutation_settings`,
     - `performance_settings`, `security_settings`, `middleware_settings`.

4. **Fix RBAC and field permission defects.**
   - `rail_django/security/rbac.py` uses `Group.objects.get` before group creation when checking max users.
   - `rail_django/security/field_permissions.py` references `model_class` without defining it in `field_permission_required`.

5. **Remove dead code or document limitations.**
   - Multiple "caching removed" comments remain, but config and code paths still expose caching flags. Either reintroduce caching or remove flags/docs.

## Suggested Implementation Plan
### Immediate (1-2 days)
- Wire GraphQL middleware into `MultiSchemaGraphQLView` and GraphQLView.
- Add auth/permission checks to schema management and export endpoints.
- Fix the `optimization.py` indentation bug and `CachingMiddleware` reference.
- Enforce token type in JWT verification.

### Short Term (1-2 weeks)
- Consolidate performance middleware and optimizer modules.
- Align settings keys and update docs/examples.
- Add export row limits, whitelists, and streaming.
- Replace in-memory rate limiting with Django cache or Redis.

### Medium Term
- Add dataloader support and selection-set driven prefetch.
- Add security-focused tests for auth, rate limits, and schema management.
- Add performance benchmarks with representative schemas.

## Suggested Tests to Add
- GraphQL middleware integration tests (rate limit, validation, complexity).
- JWT type enforcement tests (refresh token rejected for access).
- Export permission tests (model/field allowlist).
- Schema management endpoint auth tests.
