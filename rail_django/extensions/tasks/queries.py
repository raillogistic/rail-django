"""
GraphQL query types for tasks.
"""

from typing import Optional
import graphene
from django.db.models import Q
from django.utils import timezone
from graphene.types.generic import GenericScalar
from graphql import GraphQLError

from ...config_proxy import get_setting
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
    progress_message = graphene.String()
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

    @staticmethod
    def resolve_progress_message(root, info):
        metadata = getattr(root, "metadata", None)
        if isinstance(metadata, dict):
            value = metadata.get("progress_message")
            if value is None:
                return None
            return str(value)
        return None


class TaskQuery(graphene.ObjectType):
    task = graphene.Field(TaskExecutionPayloadType, id=graphene.ID(required=True))
    tasks = graphene.List(
        TaskExecutionPayloadType,
        status=graphene.String(required=False),
        limit=graphene.Int(required=False),
    )

    def resolve_task(self, info, id: str):
        schema_name = _resolve_schema_name(info)
        settings = get_task_settings(schema_name)
        if not settings.enabled:
            raise GraphQLError("Task orchestration is disabled.")

        task = TaskExecution.objects.filter(pk=id).first()
        if (
            not task
            or _task_is_expired(task)
            or not _task_matches_schema(task, schema_name)
        ):
            raise GraphQLError("Task not found.")
        if not _task_access_allowed(info.context, task, schema_name):
            raise GraphQLError("Task not found.")
        return task

    def resolve_tasks(
        self,
        info,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ):
        schema_name = _resolve_schema_name(info)
        settings = get_task_settings(schema_name)
        if not settings.enabled:
            raise GraphQLError("Task orchestration is disabled.")

        queryset = TaskExecution.objects.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        )
        if status:
            queryset = queryset.filter(status=str(status).upper())
        queryset = _filter_queryset_for_user(info.context, queryset, schema_name)
        if schema_name == "default":
            queryset = queryset.filter(
                Q(metadata__schema_name="default")
                | Q(metadata__schema_name__isnull=True)
            )
        else:
            queryset = queryset.filter(metadata__schema_name=schema_name)

        max_limit = int(get_setting("query_settings.max_page_size", 100, schema_name))
        default_limit = int(
            get_setting("query_settings.default_page_size", 20, schema_name)
        )
        resolved_limit = default_limit if limit is None else int(limit)
        resolved_limit = max(1, min(resolved_limit, max_limit))
        return list(queryset[:resolved_limit])
