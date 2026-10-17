# GraphQL performance without result caching

The October 2026 performance changes reduce repeated database reads and repeated
operation analysis. They add no response, permission, tenant, query-plan, or AST
cache. Existing authentication, object and field permissions, input validation,
transaction boundaries, model saves, and signals still run.

## Relation loading

The selection analyzer follows the actual GraphQL return type through `items`,
`edges`, `node`, `object`, and `objects`. An items-only paginated query receives
the same relation planning as one selecting `pageInfo`. Aliases, fragments,
`@skip`, and `@include` are considered when determining requested relations.
CamelCase relation names map to their Django field names. Custom payloads and
custom field names still need their own resolver and query-count coverage.

List, paginated, and single queries apply the existing queryset optimizer.
Create, update, bulk-create, and bulk-update response fields prefetch selected
relations onto the saved objects. The response loader does not refetch those
root objects, discard unsaved hook changes, or replace the write pipeline.
Delete and custom method mutation outputs keep their existing behavior.

`performance_settings.enable_query_optimization`, `enable_select_related`,
`enable_prefetch_related`, and `max_prefetch_depth` control this work. The depth
setting now bounds traversal beyond the first collection; zero disables automatic
prefetch paths. Deep or high-fanout selections still need resource limits and
production-cardinality measurements. Eager loading can retain more related rows
at once even when it reduces SQL statements.

When a selected computed/custom field has unknown column dependencies, the
optimizer loads all root columns instead of using an unsafe `only()` selection.
This avoids one deferred-column query per object. It can increase bytes read for
wide models. Properties that issue their own database queries still require
application-specific annotations or explicit relation planning.

## Tenant enforcement on prefetched collections

Generated many-to-many, reverse, and generic relation resolvers now apply tenant
scope to prefetched querysets, including generic relation counts. Previously the
prefetched shortcut could return rows without this check. With tenant isolation
enabled, callers can now receive fewer related rows or a tenant-context error.
This is a security correction, not a compatibility promise.

Tenant filtering may execute another query for each parent collection because a
scoped queryset cannot safely reuse an unscoped prefetched result. Do not remove
this enforcement to reach a query-count target. Benchmark tenant-aware schemas
separately. Disabled tenancy and models without a tenant field avoid parsing the
complete multitenancy settings on each scalar/relation path; settings are still
read through the existing configuration system.

## Nested writes

Nested many-to-many `set` and reverse-FK `set` batch preflight object lookups
through the tenant-scoped queryset. Permission and tenant checks still run for
every input in order. Reverse-FK changes retain individual `full_clean()` and
`save()` calls and the existing atomic block. A validation failure still rolls
back database changes and prevents commit callbacks from running.

An overridden `_resolve_related_instance`, duplicate IDs, or malformed ID
coercion uses the existing individual lookup path. Interleaved connect,
disconnect, update, and bulk-update write lookups are deliberately not batched:
an earlier save hook can affect later objects or their visibility. This change
does not replace validated saves with SQL `bulk_update()` or `bulk_create()`.

Mutation output relation loading takes place during field serialization, after
the existing write transaction returns. A later serialization error does not
roll back a committed mutation. Applications must not rely on response
serialization as a transaction boundary.

## Pagination and computed ordering

Metadata-only pagination does not fetch unused items. Exact counts and page
clamping remain in force. `skipCount: true` keeps its existing unknown-total
contract and uses a bounded existence query when only next-page metadata is
selected. Selecting `items { __typename }` still returns the correct number of
items. These are internal SQL changes; they add no GraphQL arguments or types.

Ordinary lists sorted by a Python property no longer issue a count that their
response cannot expose. They load the existing capped candidate set, plus one
row to detect truncation, before applying the property sort. Deferred columns
are cleared so property access can read the row without hidden fetches. Exact
paginated totals are retained. The existing property-ordering cap still means
sorting a subset of candidates, not a guaranteed global ordering across an
unbounded table.

## Operation analysis

`MultiSchemaGraphQLView` defaults to
`rail_django.core.execution.RailExecutionContext`. It validates selected query
operations once for each exact stock `QueryComplexityMiddleware` instance,
instead of once for every matching root alias. It uses the existing AST and
limit analyzer. No decision is retained between executions. Configured
`security_settings.limited_query_fields` selection rules still apply.

On rejection, matching root fields receive the same GraphQL field errors and
unprotected sibling fields retain their existing behavior. Authentication,
rate limiting, object/field authorization, and other middleware remain in the
chain. Successful stock complexity checks are removed from that execution's
per-field chain after validation. Subclasses of the middleware keep their own
resolver behavior. Explicit view execution contexts and class overrides are
preserved.

Direct Graphene execution can select the same behavior explicitly:

```python
from rail_django.core.execution import RailExecutionContext

result = schema.execute(
    query,
    context_value=request,
    middleware=middleware,
    execution_context_class=RailExecutionContext,
)
```

Applications with custom execution contexts should review composition instead
of replacing them blindly. This integration targets graphql-core 3.2 execution
interfaces; test another graphql-core series before upgrading. Custom
complexity analyzers overriding `validate_query_limits` need to accept the
optional `metrics` keyword if installed on the stock middleware. Query depth
and complexity metrics now come from the same validation pass. Root-resolver
timings exclude operation prevalidation; compare complete HTTP latency when
assessing total request cost.

## Reproducing measurements

Use isolated test settings and an isolated database. Never point these test
settings at application data. The opt-in workload file is not collected by the
normal `test_*.py` pattern:

```powershell
$env:DJANGO_SETTINGS_MODULE = 'your_isolated_test_settings'
$env:RAIL_PERF_OUTPUT_DIR = 'C:\temp\rail-perf-results'
python -m pytest tests/benchmarks/graphql_workloads.py -q -s --reuse-db
```

The real HTTP regression normally runs three requests, including a denied user.
To measure it, set `RAIL_PERF_HTTP_SAMPLES` to `100` and
`RAIL_PERF_HTTP_OUTPUT` to a writable JSON filename before running
`tests/integration/test_graphql_http_performance.py`. Its synthetic schema uses
JWT authentication, model/field checks, and a dummy cache backend. Rate limiting
and query logging are disabled only within that fixture to allow repetition.

Compare the same script, data size, schema, settings, database durability,
warmup, and sample count against both revisions. Record full HTTP latency as
well as SQL statements. Do not infer production throughput or latency
percentiles from these small local samples. Production operation replay,
tenant-aware workloads, wide rows, peak memory, lock contention, and the CI
runtime matrix remain separate release checks.
