# Tasks Extension

Module: `rail_django.extensions.tasks`

- Run long-running mutations asynchronously.
- Track status, progress, result, and errors in `TaskExecution`.
- Query task status via GraphQL or REST.
- Optional `taskUpdated` subscriptions when `channels-graphql-ws` is installed.

## Enable

```python
RAIL_DJANGO_GRAPHQL = {
    "task_settings": {
        "enabled": True,
        "backend": "thread",  # thread, sync, celery, dramatiq, django_q
        "default_queue": "default",
        "result_ttl_seconds": 86400,
        "max_retries": 3,
        "retry_backoff": True,
        "track_in_database": True,
        "emit_subscriptions": True,
    }
}
```

Use `backend = "sync"` to run tasks inline during tests.

## Define a task mutation

```python
import graphene
from rail_django.extensions.tasks import task_mutation

@task_mutation(name="generate_report", track_progress=True)
def generate_report(root, info, dataset_id: str):
    info.context.task.update_progress(25)
    # long-running work here
    return {"ok": True, "dataset_id": dataset_id}


class TaskMutations(graphene.ObjectType):
    generate_report = generate_report


RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "mutation_extensions": ["myapp.graphql.TaskMutations"],
    },
    "task_settings": {
        "enabled": True,
    },
}
```

## GraphQL API

GraphQL fields are snake_case by default. If `auto_camelcase` is enabled,
use camelCase versions like `taskId` and `taskUpdated`.

```graphql
mutation {
  generate_report(dataset_id: "123") {
    taskId
    status
  }
}

query {
  task(id: "abc-123") {
    id
    status
    progress
    result
    error
    created_at
    completed_at
  }
}
```

## Subscriptions

```graphql
subscription {
  taskUpdated(taskId: "abc-123") {
    status
    progress
    result
    error
  }
}
```

`taskUpdated` uses the same Channels stack as model subscriptions and requires
`channels-graphql-ws`.

## REST polling

`GET /api/v1/tasks/<uuid>/` returns status for a task.

## Dependencies

Optional backends:

- `celery`
- `dramatiq`
- `django-q`

Subscriptions require `channels-graphql-ws`.
