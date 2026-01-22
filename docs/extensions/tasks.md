# Background Tasks

Offload heavy store operations like inventory synchronization or bulk email sending to background workers.

## Usage

### 1. Define a Task Mutation

```python
# store/tasks.py
from rail_django.extensions.tasks import task_mutation

@task_mutation(name="syncInventory", track_progress=True)
def sync_inventory_task(info, provider: str):
    task = info.context.task
    
    task.update_progress(10)
    # Fetch from external API
    products = external_api.get_stock(provider)
    
    task.update_progress(50)
    # Update local database
    for p in products:
        Product.objects.filter(sku=p.sku).update(inventory_count=p.stock)
        
    task.update_progress(100)
    return {"updated": len(products)}
```

### 2. Register and Call

```python
register_mutation(sync_inventory_task)
```

```graphql
mutation {
  syncInventory(provider: "AMAZON") {
    taskId
    status
  }
}
```

## Tracking Progress

Use GraphQL Subscriptions to show real-time progress in your frontend.

```graphql
subscription {
  taskUpdated(taskId: "...") {
    progress
    status
    result
  }
}
```

## Backends

Configure your preferred worker in `settings.py`:

```python
RAIL_DJANGO_GRAPHQL = {
    "task_settings": {
        "backend": "celery", # or 'thread', 'dramatiq'
        "default_queue": "store_tasks"
    }
}
```
