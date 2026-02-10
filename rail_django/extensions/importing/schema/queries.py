"""Import query root definitions."""

from __future__ import annotations

import graphene

from ..models import ImportBatch
from ..services import (
    get_import_batch,
    list_import_batches,
    require_import_access,
    resolve_template_descriptor,
)
from .types import (
    ImportBatchStatusEnum,
    ImportErrorReportFormatEnum,
    ImportFileDownloadType,
    ModelImportBatchPageType,
    ModelImportBatchType,
    ModelImportTemplateType,
)


def _enum_value(value):
    return getattr(value, "value", value)


class ImportQuery(graphene.ObjectType):
    model_import_template = graphene.Field(
        ModelImportTemplateType,
        app_label=graphene.String(required=True),
        model_name=graphene.String(required=True),
    )
    model_import_batch = graphene.Field(
        ModelImportBatchType,
        batch_id=graphene.ID(required=True),
    )
    model_import_batch_pages = graphene.Field(
        ModelImportBatchPageType,
        page=graphene.Int(default_value=1),
        per_page=graphene.Int(default_value=50),
        app_label=graphene.String(),
        model_name=graphene.String(),
        status=ImportBatchStatusEnum(),
    )
    model_import_error_report = graphene.Field(
        ImportFileDownloadType,
        batch_id=graphene.ID(required=True),
        format=ImportErrorReportFormatEnum(default_value="CSV"),
    )

    def resolve_model_import_template(self, info, app_label: str, model_name: str):
        user = getattr(info.context, "user", None)
        require_import_access(user, app_label=app_label, model_name=model_name)
        return resolve_template_descriptor(app_label=app_label, model_name=model_name)

    def resolve_model_import_batch(self, info, batch_id: str):
        batch = get_import_batch(batch_id)
        if batch is None:
            return None
        user = getattr(info.context, "user", None)
        require_import_access(user, app_label=batch.app_label, model_name=batch.model_name)
        return batch

    def resolve_model_import_batch_pages(
        self,
        info,
        page=1,
        per_page=50,
        app_label=None,
        model_name=None,
        status=None,
    ):
        safe_page = max(1, int(page))
        safe_per_page = max(1, min(int(per_page), 200))
        user = getattr(info.context, "user", None)
        if app_label and model_name:
            require_import_access(user, app_label=app_label, model_name=model_name)

        total, results = list_import_batches(
            page=safe_page,
            per_page=safe_per_page,
            app_label=app_label,
            model_name=model_name,
            status=_enum_value(status),
        )
        return {
            "page": safe_page,
            "per_page": safe_per_page,
            "total": total,
            "results": results,
        }

    def resolve_model_import_error_report(self, info, batch_id: str, format="CSV"):
        batch = (
            ImportBatch.objects.filter(id=batch_id)
            .only("id", "app_label", "model_name", "error_report_path")
            .first()
        )
        if batch is None:
            return None

        user = getattr(info.context, "user", None)
        require_import_access(user, app_label=batch.app_label, model_name=batch.model_name)

        if not batch.error_report_path:
            return None

        return {
            "file_name": f"import-errors-{batch.id}.{str(_enum_value(format)).lower()}",
            "content_type": "text/csv",
            "download_url": batch.error_report_path,
            "expires_at": None,
        }
