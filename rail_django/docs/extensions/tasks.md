# Background Tasks

Rail Django includes a powerful background task system for offloading long-running operations asynchronously, providing real-time progress tracking and reliable execution.

## Overview

The background task system provides:
- Multiple backends (Celery, Dramatiq, Django-Q, Threads).
- Automatic GraphQL mutation generation for tasks.
- Real-time progress and status tracking via subscriptions.
- Persistent task logs and result retention.
- Automatic retries with backoff.

## Configuration

Enable background tasks in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "task_settings": {
        "enabled": True,
        # Backend options: 'celery', 'dramatiq', 'django_q', 'thread', 'sync'
        "backend": "thread",
        "default_queue": "default",
        "result_ttl_seconds": 86400,  # 24 hours
        "max_retries": 3,
        "track_in_database": True,
        "emit_subscriptions": True,
    },
}
```

### Backend Options

- **Celery**: Recommended for production. Requires a Celery app configuration.
- **Dramatiq**: Modern alternative to Celery.
- **Django-Q**: Native Django task queue.
- **Thread**: Simple threading, useful for lightweight tasks or development without extra infrastructure.
- **Sync**: Executes tasks inline. Useful for testing.

## Defining Task Mutations

Use the `@task_mutation` decorator to turn a function into a background-executable GraphQL mutation.

```python
from rail_django.extensions.tasks import task_mutation

@task_mutation(name="syncInventory", track_progress=True)
def sync_inventory_task(info, provider: str):
    task = info.context.task

    task.update_progress(10, "Fetching from provider...")
    # ... logic ...

    task.update_progress(50, "Updating local database...")
    # ... logic ...

    task.update_progress(100, "Complete")
    return {"updated_count": 42}
```

### Calling from GraphQL

```graphql
mutation StartSync {
  syncInventory(provider: "AMAZON") {
    taskId
    status # PENDING, RUNNING, COMPLETED, FAILED
  }
}
```

## Tracking Progress

### GraphQL Query
You can poll for task status:

```graphql
query CheckTask($id: ID!) {
  task(id: $id) {
    status
    progress
    progressMessage
    result
    error
  }
}
```

### Subscriptions
For real-time updates, use the `taskProgress` subscription:

```graphql
subscription OnTaskUpdate($taskId: ID!) {
  taskProgress(taskId: $taskId) {
    status
    progress
    progressMessage
  }
}
```

## Best Practices

### 1. Idempotency
Ensure your tasks can be safely retried. Check for already-processed data at the start of the task.

### 2. Update Progress Frequently
For tasks taking more than a few seconds, provide regular progress updates to improve user experience.

### 3. Use Appropriate Queues
Separate fast, urgent tasks from slow, heavy background jobs using different queues.

```python
@task_mutation(queue="urgent")
def send_notification(info, message: str):
    pass
```

## See Also

- [Subscriptions](./subscriptions.md) - For real-time updates.
- [Observability](./observability.md) - For monitoring task performance.
- [Configuration Reference](../reference/configuration.md)
