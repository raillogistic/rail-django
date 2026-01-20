# Background Tasks

## Overview

Rail Django includes a background task system for executing long-running operations asynchronously. This guide covers configuration, task creation, status tracking, and best practices.

---

## Table of Contents

1. [Configuration](#configuration)
2. [Backend Options](#backend-options)
3. [Creating Tasks](#creating-tasks)
4. [GraphQL Mutations](#graphql-mutations)
5. [Task Status Tracking](#task-status-tracking)
6. [Subscriptions](#subscriptions)
7. [Error Handling](#error-handling)
8. [Best Practices](#best-practices)

---

## Configuration

### Basic Configuration

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "task_settings": {
        # Enable background tasks
        "enabled": True,

        # Backend: thread, sync, celery, dramatiq, django_q
        "backend": "thread",

        # Default queue
        "default_queue": "default",

        # Result retention (seconds)
        "result_ttl_seconds": 86400,  # 24 hours

        # Retry configuration
        "max_retries": 3,
        "retry_backoff": True,

        # Database tracking
        "track_in_database": True,

        # Emit subscription events
        "emit_subscriptions": True,
    },
}
```

---

## Backend Options

### Thread Backend (Development)

Simple threading for development and testing:

```python
"task_settings": {
    "backend": "thread",
    "max_workers": 4,
}
```

### Sync Backend (Testing)

Executes tasks synchronously (inline):

```python
"task_settings": {
    "backend": "sync",
}
```

Use `backend = "sync"` in tests to run tasks inline.

### Celery Backend (Production)

For production with Celery:

```python
# settings.py
"task_settings": {
    "backend": "celery",
    "celery_app": "root.celery.app",
}

# root/celery.py
from celery import Celery

app = Celery("myproject")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

### Dramatiq Backend

For production with Dramatiq:

```python
"task_settings": {
    "backend": "dramatiq",
}
```

### Django-Q Backend

For production with Django-Q:

```python
"task_settings": {
    "backend": "django_q",
}
```

---

## Creating Tasks

### Task Mutation Decorator

```python
import graphene
from rail_django.extensions.tasks import task_mutation

@task_mutation(name="generate_report", track_progress=True)
def generate_report(root, info, dataset_id: str):
    """
    Generate a report asynchronously.

    Args:
        dataset_id: The dataset identifier.

    Returns:
        Task result.
    """
    # Update progress
    info.context.task.update_progress(25, "Fetching data...")
    data = fetch_data(dataset_id)

    info.context.task.update_progress(50, "Processing...")
    processed = process_data(data)

    info.context.task.update_progress(75, "Generating file...")
    file_path = create_report(processed)

    info.context.task.update_progress(100, "Complete")
    return {"ok": True, "file_path": file_path}


class TaskMutations(graphene.ObjectType):
    generate_report = generate_report
```

### Register Task Mutations

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "mutation_extensions": ["myapp.graphql.TaskMutations"],
    },
}
```

### Task Options

```python
@task_mutation(
    name="process_order",
    queue="orders",
    max_retries=5,
    retry_delay=60,
    timeout=300,
    track_progress=True,
)
def process_order(root, info, order_id: str):
    """
    Process an order asynchronously.
    """
    order = Order.objects.get(pk=order_id)
    # ... processing logic
    return {"ok": True, "status": "processed"}
```

---

## GraphQL Mutations

### Execute Task

```graphql
mutation GenerateReport($datasetId: String!) {
  generateReport(datasetId: $datasetId) {
    taskId
    status
  }
}
```

### Response

```json
{
  "data": {
    "generateReport": {
      "taskId": "abc-123-xyz",
      "status": "pending"
    }
  }
}
```

---

## Task Status Tracking

### GraphQL Query

```graphql
query TaskStatus($taskId: ID!) {
  task(id: $taskId) {
    id
    name
    status
    progress
    progressMessage
    result
    error
    createdAt
    startedAt
    completedAt
  }
}
```

### Status Values

| Status      | Description                  |
| ----------- | ---------------------------- |
| `pending`   | Task queued, not yet started |
| `running`   | Task currently executing     |
| `completed` | Task finished successfully   |
| `failed`    | Task failed with error       |
| `cancelled` | Task was cancelled           |
| `retrying`  | Task failed, awaiting retry  |

### REST Endpoint

```bash
curl /api/v1/tasks/<uuid>/ \
  -H "Authorization: Bearer <jwt>"
```

```json
{
  "id": "abc-123-xyz",
  "name": "generate_report",
  "status": "running",
  "progress": 50,
  "progress_message": "Processing...",
  "created_at": "2026-01-16T12:00:00Z",
  "started_at": "2026-01-16T12:00:05Z"
}
```

---

## Subscriptions

Real-time task updates require `channels-graphql-ws`.

### Task Status Subscription

```graphql
subscription TaskProgress($taskId: ID!) {
  taskProgress(taskId: $taskId) {
    id
    status
    progress
    progressMessage
    result
    error
  }
}
```

### All User Tasks

```graphql
subscription MyTasks {
  myTaskUpdates {
    id
    name
    status
    progress
  }
}
```

### Configuration

```python
"task_settings": {
    "emit_subscriptions": True,
    "subscription_channel": "tasks",
}
```

---

## Error Handling

### Retry Configuration

```python
@task_mutation(
    max_retries=3,
    retry_delay=60,  # seconds
    retry_backoff=True,  # exponential backoff
)
def flaky_external_call(root, info, data: str):
    """
    Task with automatic retry on failure.
    """
    return external_api.call(data)
```

### Error Tracking

```graphql
query FailedTasks {
  tasks(status: "failed", limit: 50) {
    id
    name
    error
    retryCount
    createdAt
  }
}
```

### Notification on Failure

```python
"task_settings": {
    "on_failure": "callback",
    "failure_callback": "myapp.tasks.on_task_failed",
}

# myapp/tasks.py
def on_task_failed(taskId, task_name, error, traceback):
    """
    Called when a task fails after all retries.
    """
    send_alert(
        f"Task {task_name} failed",
        details={"taskId": taskId, "error": str(error)}
    )
```

---

## Best Practices

### 1. Keep Tasks Idempotent

```python
@task_mutation
def process_payment(root, info, payment_id: str):
    payment = Payment.objects.get(pk=payment_id)

    # Skip if already processed
    if payment.status == "completed":
        return {"ok": True, "already_processed": True}

    # Process payment
    result = payment_gateway.charge(payment)
    payment.status = "completed"
    payment.save()

    return {"ok": True, "result": result}
```

### 2. Track Progress for Long Tasks

```python
@task_mutation(track_progress=True)
def bulk_import(root, info, file_path: str):
    records = read_file(file_path)
    total = len(records)

    for i, record in enumerate(records):
        process_record(record)
        progress = int((i + 1) / total * 100)
        info.context.task.update_progress(
            progress, f"Processed {i + 1}/{total}"
        )

    return {"ok": True, "imported": total}
```

### 3. Use Queues for Priority

```python
# High priority tasks
@task_mutation(queue="high")
def urgent_notification(root, info):
    pass

# Low priority tasks
@task_mutation(queue="low")
def cleanup_old_files(root, info):
    pass
```

### 4. Set Appropriate Timeouts

```python
@task_mutation(timeout=60)  # 1 minute
def quick_task(root, info):
    pass

@task_mutation(timeout=3600)  # 1 hour
def long_running_report(root, info):
    pass
```

### 5. Clean Up Old Tasks

```bash
# Management command
python manage.py cleanup_tasks --days 7
```

### 6. Monitor Task Performance

```python
"task_settings": {
    "metrics_enabled": True,
    "log_task_start": True,
    "log_task_complete": True,
    "slow_task_threshold_seconds": 60,
}
```

---

## See Also

- [Subscriptions](./subscriptions.md) - Real-time task updates
- [Audit & Logging](./audit.md) - Task event tracking
- [Configuration](../graphql/configuration.md) - task_settings
