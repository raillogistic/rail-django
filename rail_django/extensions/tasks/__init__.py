"""
Background task orchestration helpers.
"""

from .config import TaskSettings, get_task_settings, tasks_enabled
from .executor import (
    TaskExecutionHandle,
)
from .models import TaskExecution, TaskStatus
from .mutations import task_mutation
from .queries import TaskExecutionPayloadType, TaskQuery
from .utils import (
    _snapshot_context,
    _update_task_execution,
    get_task_subscription_field,
)
from .views import TaskStatusView, get_task_urls

__all__ = [
    # Config
    "TaskSettings",
    "get_task_settings",
    "tasks_enabled",
    # Models
    "TaskExecution",
    "TaskStatus",
    # Handle
    "TaskExecutionHandle",
    # Mutations
    "task_mutation",
    # Queries
    "TaskExecutionPayloadType",
    "TaskQuery",
    # Subscriptions
    "get_task_subscription_field",
    # Views
    "TaskStatusView",
    # URLs
    "get_task_urls",
    # Internal utilities (exported for compatibility if needed)
    "_snapshot_context",
    "_update_task_execution",
]
