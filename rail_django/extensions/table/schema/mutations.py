"""Table v3 mutation definitions."""

import graphene
from graphql import GraphQLError

from .inputs import (
    BulkEditInput,
    ExecuteTableActionInput,
    SaveTableViewInput,
    ScheduleExportInput,
)
from .types import (
    BulkEditResultType,
    SaveTableViewResultType,
    ScheduleExportResultType,
    TableActionResultType,
)
from ..services.action_executor import execute_table_action
from ..services.bulk_edit import apply_bulk_edit
from ..services.export_scheduler import schedule_export
from ..services.view_store import save_view
from ..security.access import (
    get_table_permissions,
    resolve_table_model,
    table_mutations_enabled,
)


class ExecuteTableActionMutation(graphene.Mutation):
    class Arguments:
        input = ExecuteTableActionInput(required=True)

    Output = TableActionResultType

    def mutate(self, info, input):
        return execute_table_action(input, user=getattr(info.context, "user", None))


class TableMutations(graphene.ObjectType):
    executeTableAction = ExecuteTableActionMutation.Field()
    saveTableView = graphene.Field(
        SaveTableViewResultType,
        input=SaveTableViewInput(required=True),
    )
    executeBulkEdit = graphene.Field(
        BulkEditResultType,
        input=BulkEditInput(required=True),
    )
    scheduleTableExport = graphene.Field(
        ScheduleExportResultType,
        input=ScheduleExportInput(required=True),
    )

    def resolve_saveTableView(self, info, input):
        if not table_mutations_enabled():
            raise GraphQLError("Table mutations are disabled.")
        user = getattr(info.context, "user", None)
        model_cls = resolve_table_model(input["app"], input["model"])
        permissions = get_table_permissions(user, model_cls)
        if not permissions.can_view:
            raise GraphQLError("Permission denied.")
        if not user or not getattr(user, "is_authenticated", False):
            raise GraphQLError("Authentication required.")
        view = save_view(
            app=input["app"],
            model=input["model"],
            name=input["name"],
            config=input.get("config"),
            is_public=input.get("isPublic", False),
        )
        return {"ok": True, "view": view}

    def resolve_executeBulkEdit(self, info, input):
        return apply_bulk_edit(
            app=input["app"],
            model=input["model"],
            row_ids=input["rowIds"],
            changes=input["changes"] or {},
            user=getattr(info.context, "user", None),
        )

    def resolve_scheduleTableExport(self, info, input):
        return schedule_export(
            app=input["app"],
            model=input["model"],
            export_format=input.get("format"),
            user=getattr(info.context, "user", None),
        )
