"""Table v3 query definitions."""

import graphene

from .inputs import TableRowsInput
from .types import TableBootstrapMinimalType, TableBootstrapType, TableRowsType
from ..services.bootstrap import build_table_bootstrap_payload
from ..services.data_resolver import resolve_table_rows
from ..services.progressive_loader import build_minimal_bootstrap


class TableQuery(graphene.ObjectType):
    tableBootstrap = graphene.Field(
        TableBootstrapType,
        app=graphene.String(required=True),
        model=graphene.String(required=True),
        view=graphene.String(),
        persistenceKey=graphene.String(),
        objectId=graphene.ID(),
    )

    tableRows = graphene.Field(TableRowsType, input=TableRowsInput(required=True))
    tableBootstrapMinimal = graphene.Field(
        TableBootstrapMinimalType,
        app=graphene.String(required=True),
        model=graphene.String(required=True),
        persistenceKey=graphene.String(),
    )

    def resolve_tableBootstrap(
        self,
        info,
        app: str,
        model: str,
        view=None,
        persistenceKey=None,
        objectId=None,
    ):
        payload = build_table_bootstrap_payload(
            app,
            model,
            user=getattr(info.context, "user", None),
            persistence_key=persistenceKey,
        )
        payload["firstPage"] = resolve_table_rows(
            {"app": app, "model": model},
            info=info,
        )
        return payload

    def resolve_tableRows(self, info, input):
        return resolve_table_rows(input, info=info)

    def resolve_tableBootstrapMinimal(
        self,
        info,
        app: str,
        model: str,
        persistenceKey=None,
    ):
        payload = build_table_bootstrap_payload(
            app,
            model,
            user=getattr(info.context, "user", None),
            persistence_key=persistenceKey,
        )
        return build_minimal_bootstrap(payload)
