# Audit security and compatibility update

This change implements the runtime corrections RD-001 through RD-013 from the October 2026 audit. It changes previously unsafe behavior. Applications need the checks below before deployment; passing the framework tests is not a universal compatibility guarantee.

## Supported runtime

Django 5.2.18 is the new minimum security baseline. Django 5.0 and 5.1 are no longer supported. Python 3.11 and 3.12 remain the CI targets. Later Django series may resolve under the dependency declaration, but are not claimed tested by this update.

The minimum includes the October security fixes described in the [Django 5.2.18 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2.18/). Keep deployment constraints on maintained patched releases. Package dependencies in pyproject.toml and scaffold application requirements have different purposes. Only the subscriptions extra is defined.

## Resolver result caching (RD-001)

optimize_query retains its arguments and queryset optimization/monitoring behavior. Resolver result caching is bypassed, including when enable_caching or enable_query_caching is set. Arbitrary resolvers perform their own authorization, which cannot safely be skipped on a hit. Existing cache backend APIs remain available for explicit application uses.

Expect more resolver executions and different latency if this cache was enabled. No safe public-resolver contract or measured benefit has yet justified automatic cache restoration. Do not re-enable it with a key-only patch. Clear old result namespaces when deploying.

## Tenant selection (RD-004)

Trusted request.tenant_id/request.tenant and verified jwt_payload tenant claims retain precedence. A client header or subdomain now requires an authenticated user and an explicit application authorizer. Empty tenant_header disables header fallback.

Configure multitenancy_settings.tenant_authorizer with a callable or dotted import path. Its signature is:

```python
def authorize_tenant(request, tenant_id, *, schema_name=None):
    # Consult the application's authoritative membership records.
    return membership_service.can_select(request.user, tenant_id)
```

Return the boolean True to allow selection. Missing configuration, anonymous users and rejected membership fail closed. Do not use an authorizer that always returns True. A proxy integration must validate membership and strip untrusted client values before installing trusted request context.

The decision is reused only within the request. WebSocket publications create a fresh context and reload authentication, so revoked membership can be rejected. Same-user/two-tenant operations must be replayed during rollout. GraphQL denial/null/error behavior depends on the operation; a universal HTTP 404 is not promised.

## Mutation and query behavior (RD-002, RD-003, RD-006, RD-011)

- Reverse nullable-FK set authorizes all removed and target children before writing, uses validated saves and is atomic. Child hooks/signals now run on detach. Permission-denied replacement is an intended security correction.
- Generated list database errors fail with a sanitized GraphQL message. They no longer retry from an unrestricted manager. Repair application migrations/configuration instead of relying on the old recovery path.
- Numeric saved-filter IDs enforce the same owner/shared/model rule as names. Inaccessible IDs preserve the unavailable-filter behavior and do not increment usage.
- A pipeline returning should_abort rolls back earlier writes and suppresses on_commit callbacks. Warning-only contexts still commit. External effects that must follow success belong in on_commit; attempt logging is a separate contract.

## HTTP authentication and CSRF (RD-005)

An Authorization header alone no longer exempts an existing session from CSRF. Session identity takes precedence in the existing API/view flows. Validated explicit header tokens are marked header_token; the existing JWT middleware continues its cookie CSRF checks.

Clients sending stale or dummy Authorization alongside session cookies may receive 401/403. Use a valid header token or the session CSRF cookie/header pair. Cookie authentication must retain CSRF protection.

## Schema lifecycle and discovery (RD-007, RD-008, RD-009)

Re-registration retains builder references and explicitly registered custom mutations, invalidates compiled state/generators and reloads settings. Removed fields can disappear immediately. Configuration propagation across workers still requires the deployment's existing restart/reload mechanism.

Schema-instance cache fills use the builder lock so concurrent rebuilds cannot label an old schema with the new version. This synchronization is process-local.

Discovery imports actual schema modules in the existing candidate order. Previously missed modules may now load or reveal collisions; dependency import failures are surfaced. Compare discovered schema names and introspection before deployment.

New scaffold projects also correct the user mutation extension path to apps.users.mutations.UsersMutations. Their generated schema now includes that intended extension. Compare its exposed fields when updating an existing project's equivalent setting.

Database registry discovery is optional by default. Missing-table/availability errors are caught during evaluation, and pending discovery is retried after rail_django migrations. Explicit discovery helpers can also be called after recovery. Set RAIL_DJANGO_DATABASE_REGISTRY_REQUIRED=True when serving settings-only definitions is unsafe: database failures then propagate, including startup discovery. Bootstrap migrations must run with the optional mode before requiring the registry.

## Subscriptions (RD-010)

The existing graphql-transport-ws protocol and generated field/event names remain. Registration stores channel groups in execution context instead of returning group lists through GraphQL object fields. The transport executes synchronous ORM work in Channels' database adapter.

get_subscription_consumer(name) still returns a class; ASGI routes must use .as_asgi(). The class now binds the supplied schema name. Clients must send connection_init before subscribe. Access tokens can be supplied as Authorization: Bearer in connection parameters or the WebSocket upgrade headers; session users can be provided by AuthMiddlewareStack. Invalid credentials/protocol/duplicate IDs are rejected. At most 100 active operations are accepted per connection.

Publication reloads user/token state, applies configured model/object/operation/field policies and tenant access, and suppresses rejected/filtered events. With object permissions enabled, the configured authorization backend must grant the object's view permission; a global permission alone is insufficient. Group membership is shared between operations until the last operation leaves. Events are scheduled on commit and capture the signal-time snapshot, including deleted IDs.

Generated event snapshots use wire-compatible values and restore Django field types during publication. Datetime precision is preserved. Verify a production channel backend independently; the local transport tests use an in-memory layer.

Use an origin validator appropriate to the deployment around AuthMiddlewareStack; cookie-authenticated WebSockets need an origin boundary. Test committed create/update/delete, rollback, revocation, two tenants and disconnect before enabling delivery.

## Release and rollback (RD-012, RD-013)

Release publication depends on the same CI workflow for the exact SHA, then builds and imports installed artifacts before tagging. Existing tags must point to that SHA. No release/tag was published as part of local implementation.

These security changes need an explicitly announced release, including the supported-Django change. Keep the last reviewed configuration and a compatible patched runtime for rollback. If reverting code, contain the vulnerable optional cache/tenant/relation/transport path instead of restoring unauthorized behavior. No automatic application-data repair or schema migration is included.
