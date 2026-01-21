"""
Task status views and URLs.
"""

from django.http import Http404, JsonResponse
from django.views import View

from .models import TaskExecution
from .config import get_task_settings
from .utils import (
    _task_is_expired,
    _task_matches_schema,
    _task_access_allowed,
)


class TaskStatusView(View):
    def get(self, request, task_id):
        schema_name = getattr(request, "schema_name", None) or "default"
        settings_obj = get_task_settings(schema_name)
        if not settings_obj.enabled:
            raise Http404("Tasks are disabled")

        task = TaskExecution.objects.filter(pk=task_id).first()
        if not task or _task_is_expired(task) or not _task_matches_schema(task, schema_name):
            raise Http404("Task not found")
        if not _task_access_allowed(request, task, schema_name):
            return JsonResponse({"error": "Task not permitted"}, status=403)

        payload = {
            "task_id": str(task.id),
            "status": task.status,
            "progress": task.progress,
            "result": task.result,
            "result_reference": task.result_reference,
            "error": task.error,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "expires_at": task.expires_at.isoformat() if task.expires_at else None,
        }
        return JsonResponse(payload)


def get_task_urls():
    from django.urls import path

    return [
        path("tasks/<uuid:task_id>/", TaskStatusView.as_view(), name="task-status"),
    ]
