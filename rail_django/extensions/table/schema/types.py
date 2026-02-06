"""GraphQL types for table v3 contracts."""

import graphene


class TableColumnType(graphene.ObjectType):
    id = graphene.String(required=True)
    accessor = graphene.String(required=True)
    label = graphene.String(required=True)
    type = graphene.String(required=True)
    width = graphene.Int()


class TableSortType(graphene.ObjectType):
    field = graphene.String(required=True)
    direction = graphene.String(required=True)


class TablePaginationConfigType(graphene.ObjectType):
    defaultPageSize = graphene.Int(required=True)


class TableConfigType(graphene.ObjectType):
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    columns = graphene.List(TableColumnType, required=True)
    defaultSort = graphene.List(TableSortType, required=True)
    quickSearchFields = graphene.List(graphene.String, required=True)
    pagination = graphene.Field(TablePaginationConfigType, required=True)


class TableInitialStateType(graphene.ObjectType):
    page = graphene.Int(required=True)
    pageSize = graphene.Int(required=True)
    ordering = graphene.List(graphene.String, required=True)


class TablePageInfoType(graphene.ObjectType):
    totalCount = graphene.Int(required=True)
    pageCount = graphene.Int(required=True)
    currentPage = graphene.Int(required=True)
    hasNextPage = graphene.Boolean(required=True)
    hasPreviousPage = graphene.Boolean(required=True)


class TableRowsType(graphene.ObjectType):
    pageInfo = graphene.Field(TablePageInfoType, required=True)
    items = graphene.JSONString(required=True)
    rowPermissions = graphene.JSONString()
    aggregate = graphene.JSONString()
    etag = graphene.String()


class TablePermissionsType(graphene.ObjectType):
    canView = graphene.Boolean(required=True)
    canCreate = graphene.Boolean(required=True)
    canExport = graphene.Boolean(required=True)


class TableBootstrapType(graphene.ObjectType):
    configVersion = graphene.String(required=True)
    modelSchemaVersion = graphene.String(required=True)
    deployVersion = graphene.String(required=True)
    tableConfig = graphene.Field(TableConfigType, required=True)
    initialState = graphene.Field(TableInitialStateType, required=True)
    firstPage = graphene.Field(TableRowsType, required=True)
    permissions = graphene.Field(TablePermissionsType, required=True)


class TableBootstrapMinimalType(graphene.ObjectType):
    configVersion = graphene.String(required=True)
    essentialConfig = graphene.Field(TableConfigType, required=True)
    permissions = graphene.Field(TablePermissionsType, required=True)


class TableActionErrorType(graphene.ObjectType):
    field = graphene.String()
    message = graphene.String(required=True)
    code = graphene.String()
    retryable = graphene.Boolean()


class TableActionResultType(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    actionId = graphene.String()
    affectedIds = graphene.List(graphene.ID)
    errors = graphene.List(TableActionErrorType)


class TableViewType(graphene.ObjectType):
    id = graphene.ID(required=True)
    name = graphene.String(required=True)
    isDefault = graphene.Boolean()
    isPublic = graphene.Boolean()
    config = graphene.JSONString()
    createdAt = graphene.String()
    updatedAt = graphene.String()


class SaveTableViewResultType(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    view = graphene.Field(TableViewType)


class BulkEditPreviewType(graphene.ObjectType):
    rowId = graphene.ID(required=True)
    field = graphene.String(required=True)
    oldValue = graphene.String()
    newValue = graphene.String()
    warnings = graphene.List(graphene.String)


class BulkEditResultType(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    affectedCount = graphene.Int(required=True)
    previewChanges = graphene.List(BulkEditPreviewType)
    errors = graphene.List(TableActionErrorType)


class ScheduleExportResultType(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    exportId = graphene.String()
    estimatedCompletionTime = graphene.String()
    notifyOnComplete = graphene.Boolean()
    downloadUrl = graphene.String()
