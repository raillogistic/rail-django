"""
GraphQL query types for tasks.
"""

from typing import Optional
import graphene
from graphene.types.generic import GenericScalar
from graphql import GraphQLError

from .models import TaskExecution
from .config import get_task_settings
from .utils import (
    _resolve_schema_name,
    _task_is_expired,
    _task_matches_schema,
    _task_access_allowed,
    _filter_queryset_for_user,
)


class TaskExecutionPayloadType(graphene.ObjectType):
    id = graphene.ID(required=True)
    name = graphene.String()
    status = graphene.String()
    progress = graphene.Int()
    result = GenericScalar()
    result_reference = graphene.String()
    error = graphene.String()
    metadata = GenericScalar()
    created_at = graphene.DateTime()
    started_at = graphene.DateTime()
    completed_at = graphene.DateTime()
    expires_at = graphene.DateTime()
    owner_id = graphene.String()
    attempts = graphene.Int()
    max_retries = graphene.Int()
    updated_at = graphene.DateTime()

    class Meta:
        name = "TaskExecution"


class TaskQuery(graphene.ObjectType):
    task = graphene.Field(TaskExecutionPayloadType, id=graphene.ID(required=True))
    tasks = graphene.List(
        TaskExecutionPayloadType,
        status=graphene.String(required=False),
        limit=graphene.Int(required=False),
    )

    @staticmethod
    def resolve_task(root, info, id: str):
        schema_name = _resolve_schema_name(info)
        settings = get_task_settings(schema_name)
        if not settings.enabled:
            raise GraphQLError("Task orchestration is disabled.")

        task = TaskExecution.objects.filter(pk=id).first()
        if not task or _task_is_expired(task) or not _task_matches_schema(task, schema_name):
            raise GraphQLError("Task not found.")
        if not _task_access_allowed(info.context, task, schema_name):
            raise GraphQLError("Task not found.")
        return task

    @staticmethod
    def resolve_tasks(root, info, status: Optional[str] = None, limit: Optional[int] = None):
        schema_name = _resolve_schema_name(info)
        settings = get_task_settings(schema_name)
        if not settings.enabled:
            raise GraphQLError("Task orchestration is disabled.")

        queryset = TaskExecution.objects.all()
        if status:
            queryset = queryset.filter(status=str(status).upper())
        queryset = _filter_queryset_for_user(info.context, queryset, schema_name)
        tasks = [task for task in queryset if _task_matches_schema(task, schema_name)]
        if limit:
            tasks = tasks[: int(limit)]
        return tasks
