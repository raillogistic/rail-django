"""Reusable GraphQL entry points for reporting runtime and studio."""

from __future__ import annotations

import re

import graphene
from graphene.types.generic import GenericScalar

from .models import ReportingExportJob
from .services import ReportingService
from .studio import ReportingStudioService


class ReportingPayload(graphene.ObjectType):
    """Common result for reporting mutations."""

    status = graphene.String(required=True)
    message = graphene.String()
    data = GenericScalar()


def _success(data=None, message=None):
    return ReportingPayload(status="success", message=message, data=data)


def _failure(exc: Exception):
    return ReportingPayload(status="error", message=str(exc), data=None)


def _snake_case(value):
    """Normalize GenericScalar camelCase objects for Python services."""
    if isinstance(value, dict):
        return {
            re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower(): _snake_case(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_snake_case(item) for item in value]
    return value


class ReportingReportBuildPayload(graphene.Mutation):
    Output = ReportingPayload

    class Arguments:
        code = graphene.String(required=True)
        filters = GenericScalar()

    def mutate(self, info, code, filters=None):
        """Build an authorized report payload."""
        try:
            return _success(
                ReportingService.build_report_payload(
                    info.context, code, filters=filters
                )
            )
        except Exception as exc:
            return _failure(exc)


class ReportingExportJobCreate(graphene.Mutation):
    Output = ReportingPayload

    class Arguments:
        report_code = graphene.String(required=True)
        format = graphene.String(required=True)
        filters = GenericScalar()

    def mutate(self, info, report_code, format, filters=None):
        """Create and execute an owner-scoped export job."""
        try:
            job = ReportingService.create_report_export(
                info.context,
                report_code,
                format_name=format,
                filters=filters,
            )
            if job.status == ReportingExportJob.ExportStatus.FAILED:
                return _failure(Exception(job.error_message or "Echec de l'export."))
            return _success(
                {
                    "jobId": str(job.pk),
                    "status": job.status,
                    "fileUrl": job.file.url if job.file else None,
                    "fileName": job.file.name.rsplit("/", 1)[-1] if job.file else None,
                    "error": job.error_message or None,
                }
            )
        except Exception as exc:
            return _failure(exc)


class _StudioMutation(graphene.Mutation):
    """Shared implementation for GenericScalar studio mutations."""

    Output = ReportingPayload
    operation = ""

    class Arguments:
        input = GenericScalar(required=True)

    def mutate(self, info, input):
        """Dispatch a GenericScalar studio input to the configured service method."""
        try:
            data = getattr(ReportingStudioService(info.context), self.operation)(
                _snake_case(input)
            )
            return _success(data)
        except Exception as exc:
            return _failure(exc)


class ReportingStudioPreviewDataset(_StudioMutation):
    operation = "preview_dataset"


class ReportingStudioSaveDataset(_StudioMutation):
    operation = "save_dataset"


class ReportingStudioPreviewVisualization(_StudioMutation):
    operation = "preview_visualization"


class ReportingStudioSaveVisualization(_StudioMutation):
    operation = "save_visualization"


class ReportingStudioPreviewReport(_StudioMutation):
    operation = "preview_report"


class ReportingStudioSaveReport(_StudioMutation):
    operation = "save_report"


class _StudioDeleteMutation(graphene.Mutation):
    Output = ReportingPayload
    operation = ""

    class Arguments:
        id = graphene.ID(required=True)

    def mutate(self, info, id):
        """Delete one studio-owned asset."""
        try:
            getattr(ReportingStudioService(info.context), self.operation)(id)
            return _success()
        except Exception as exc:
            return _failure(exc)


class ReportingStudioDeleteDataset(_StudioDeleteMutation):
    operation = "delete_dataset"


class ReportingStudioDeleteVisualization(_StudioDeleteMutation):
    operation = "delete_visualization"


class ReportingStudioDeleteReport(_StudioDeleteMutation):
    operation = "delete_report"


class ReportingQuery(graphene.ObjectType):
    """Visible reporting catalog, exports, and authoring capabilities."""

    reporting_report_list = graphene.List(GenericScalar, required=True)
    reporting_export_job_list = graphene.List(GenericScalar, required=True)
    reporting_studio_capabilities = GenericScalar()
    reporting_studio_dataset_list = graphene.List(GenericScalar, required=True)
    reporting_studio_visualization_list = graphene.List(GenericScalar, required=True)
    reporting_studio_report_list = graphene.List(GenericScalar, required=True)

    def resolve_reporting_report_list(self, info):
        """Return reports visible to the current user."""
        return ReportingService.list_reports(info.context)

    def resolve_reporting_export_job_list(self, info):
        """Return the current user's latest export jobs."""
        user = getattr(info.context, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return []
        return [
            {
                "id": str(job.pk),
                "status": job.status,
                "format": job.format,
                "fileUrl": job.file.url if job.file else None,
                "createdAt": str(job.created_at),
            }
            for job in ReportingExportJob.objects.filter(requested_by=user)[:10]
        ]

    def resolve_reporting_studio_capabilities(self, info):
        """Return authoring capabilities for the current user."""
        return ReportingStudioService(info.context).capabilities()

    def resolve_reporting_studio_dataset_list(self, info):
        """Return datasets visible in the report studio."""
        return ReportingStudioService(info.context).list_datasets()

    def resolve_reporting_studio_visualization_list(self, info):
        """Return visualizations visible in the report studio."""
        return ReportingStudioService(info.context).list_visualizations()

    def resolve_reporting_studio_report_list(self, info):
        """Return reports visible in the report studio."""
        return ReportingStudioService(info.context).list_reports()


class ReportingMutation(graphene.ObjectType):
    """Reporting runtime and safe authoring mutations."""

    reporting_report_build_payload = ReportingReportBuildPayload.Field()
    reporting_export_job_create = ReportingExportJobCreate.Field()
    reporting_studio_preview_dataset = ReportingStudioPreviewDataset.Field()
    reporting_studio_save_dataset = ReportingStudioSaveDataset.Field()
    reporting_studio_delete_dataset = ReportingStudioDeleteDataset.Field()
    reporting_studio_preview_visualization = ReportingStudioPreviewVisualization.Field()
    reporting_studio_save_visualization = ReportingStudioSaveVisualization.Field()
    reporting_studio_delete_visualization = ReportingStudioDeleteVisualization.Field()
    reporting_studio_preview_report = ReportingStudioPreviewReport.Field()
    reporting_studio_save_report = ReportingStudioSaveReport.Field()
    reporting_studio_delete_report = ReportingStudioDeleteReport.Field()


__all__ = ["ReportingMutation", "ReportingPayload", "ReportingQuery"]
