"""GraphQL input types for table v3."""

import graphene


class TableRowsInput(graphene.InputObjectType):
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    page = graphene.Int()
    pageSize = graphene.Int()
    ordering = graphene.List(graphene.String)
    quickSearch = graphene.String()
    where = graphene.JSONString()


class ExecuteTableActionInput(graphene.InputObjectType):
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    actionId = graphene.String(required=True)
    rowIds = graphene.List(graphene.ID)
    payload = graphene.JSONString()


class SaveTableViewInput(graphene.InputObjectType):
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    name = graphene.String(required=True)
    config = graphene.JSONString(required=True)
    isPublic = graphene.Boolean()


class BulkEditInput(graphene.InputObjectType):
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    rowIds = graphene.List(graphene.ID, required=True)
    changes = graphene.JSONString(required=True)


class ScheduleExportInput(graphene.InputObjectType):
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    format = graphene.String()
    filters = graphene.JSONString()
