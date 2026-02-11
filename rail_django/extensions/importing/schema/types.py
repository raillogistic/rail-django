"""GraphQL type definitions for import domain."""

from __future__ import annotations

from typing import Any

import graphene

from ..models import ImportBatch, ImportIssue, ImportRow


def _read_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


class ImportFileFormatEnum(graphene.Enum):
    CSV = "CSV"
    XLSX = "XLSX"


class ImportIssueSeverityEnum(graphene.Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ImportBatchStatusEnum(graphene.Enum):
    UPLOADED = "UPLOADED"
    PARSED = "PARSED"
    REVIEWING = "REVIEWING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATED = "VALIDATED"
    SIMULATION_FAILED = "SIMULATION_FAILED"
    SIMULATED = "SIMULATED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class ImportRowActionEnum(graphene.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"


class ImportRowStatusEnum(graphene.Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    READY = "READY"
    LOCKED = "LOCKED"
    COMMITTED = "COMMITTED"


class ImportErrorReportFormatEnum(graphene.Enum):
    CSV = "CSV"


class UpdateModelImportBatchActionEnum(graphene.Enum):
    PATCH_ROWS = "PATCH_ROWS"
    VALIDATE = "VALIDATE"
    SIMULATE = "SIMULATE"
    COMMIT = "COMMIT"


class ImportColumnRuleType(graphene.ObjectType):
    name = graphene.String(required=True)
    label = graphene.String()
    required = graphene.Boolean(required=True)
    data_type = graphene.String(required=True)
    default_value = graphene.JSONString()
    format_hint = graphene.String()
    allowed_values = graphene.List(graphene.NonNull(graphene.String))


class ModelImportTemplateType(graphene.ObjectType):
    template_id = graphene.ID(required=True)
    app_label = graphene.String(required=True)
    model_name = graphene.String(required=True)
    version = graphene.String(required=True)
    exact_version = graphene.String(required=True)
    matching_key_fields = graphene.List(graphene.NonNull(graphene.String), required=True)
    required_columns = graphene.List(graphene.NonNull(ImportColumnRuleType), required=True)
    optional_columns = graphene.List(graphene.NonNull(ImportColumnRuleType), required=True)
    accepted_formats = graphene.List(graphene.NonNull(ImportFileFormatEnum), required=True)
    max_rows = graphene.Int(required=True)
    max_file_size_bytes = graphene.Int(required=True)
    download_url = graphene.String(required=True)


class ImportIssueType(graphene.ObjectType):
    id = graphene.ID(required=True)
    row_number = graphene.Int()
    field_path = graphene.String()
    code = graphene.String(required=True)
    severity = graphene.Field(ImportIssueSeverityEnum, required=True)
    message = graphene.String(required=True)
    suggested_fix = graphene.String()
    stage = graphene.String(required=True)

    @classmethod
    def is_type_of(cls, root, info):
        return isinstance(root, (cls, ImportIssue, dict))

    def resolve_severity(self, info):
        value = _read_value(self, "severity")
        return getattr(value, "value", value)

    @staticmethod
    def from_model(issue: ImportIssue) -> dict[str, Any]:
        return {
            "id": str(issue.id),
            "row_number": issue.row_number,
            "field_path": issue.field_path,
            "code": issue.code,
            "severity": issue.severity,
            "message": issue.message,
            "suggested_fix": issue.suggested_fix,
            "stage": issue.stage,
        }


class ModelImportRowType(graphene.ObjectType):
    id = graphene.ID(required=True)
    row_number = graphene.Int(required=True)
    edited_values = graphene.JSONString(required=True)
    normalized_values = graphene.JSONString()
    matching_key = graphene.String()
    action = graphene.Field(ImportRowActionEnum, required=True)
    status = graphene.Field(ImportRowStatusEnum, required=True)
    issue_count = graphene.Int(required=True)
    updated_at = graphene.DateTime(required=True)

    @classmethod
    def is_type_of(cls, root, info):
        return isinstance(root, (cls, ImportRow, dict))

    def resolve_action(self, info):
        value = _read_value(self, "action")
        if value not in {"CREATE", "UPDATE"}:
            return "CREATE"
        return getattr(value, "value", value)

    def resolve_status(self, info):
        value = _read_value(self, "status")
        if value not in {"VALID", "INVALID", "READY", "LOCKED", "COMMITTED"}:
            return "INVALID"
        return getattr(value, "value", value)

    @staticmethod
    def from_model(row: ImportRow) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "row_number": row.row_number,
            "edited_values": row.edited_values,
            "normalized_values": row.normalized_values,
            "matching_key": row.matching_key,
            "action": row.action,
            "status": row.status,
            "issue_count": row.issue_count,
            "updated_at": row.updated_at,
        }


class ImportValidationSummaryType(graphene.ObjectType):
    total_rows = graphene.Int(required=True)
    valid_rows = graphene.Int(required=True)
    invalid_rows = graphene.Int(required=True)
    blocking_issues = graphene.Int(required=True)
    warnings = graphene.Int(required=True)


class ImportSimulationSummaryType(graphene.ObjectType):
    can_commit = graphene.Boolean(required=True)
    would_create = graphene.Int(required=True)
    would_update = graphene.Int(required=True)
    blocking_issues = graphene.Int(required=True)
    warnings = graphene.Int(required=True)
    duration_ms = graphene.Int(required=True)


class ImportCommitSummaryType(graphene.ObjectType):
    total_rows = graphene.Int(required=True)
    committed_rows = graphene.Int(required=True)
    create_rows = graphene.Int(required=True)
    update_rows = graphene.Int(required=True)
    skipped_rows = graphene.Int(required=True)


class ImportFileDownloadType(graphene.ObjectType):
    file_name = graphene.String(required=True)
    content_type = graphene.String(required=True)
    download_url = graphene.String(required=True)
    expires_at = graphene.DateTime()


class ModelImportBatchType(graphene.ObjectType):
    id = graphene.ID(required=True)
    app_label = graphene.String(required=True)
    model_name = graphene.String(required=True)
    template_id = graphene.ID(required=True)
    template_version = graphene.String(required=True)
    status = graphene.Field(ImportBatchStatusEnum, required=True)
    total_rows = graphene.Int(required=True)
    valid_rows = graphene.Int(required=True)
    invalid_rows = graphene.Int(required=True)
    create_rows = graphene.Int(required=True)
    update_rows = graphene.Int(required=True)
    committed_rows = graphene.Int(required=True)
    created_at = graphene.DateTime(required=True)
    updated_at = graphene.DateTime(required=True)
    submitted_at = graphene.DateTime()
    committed_at = graphene.DateTime()
    rows = graphene.List(
        graphene.NonNull(ModelImportRowType),
        page=graphene.Int(default_value=1),
        per_page=graphene.Int(default_value=100),
    )
    issues = graphene.List(
        graphene.NonNull(ImportIssueType),
        page=graphene.Int(default_value=1),
        per_page=graphene.Int(default_value=200),
        severity=ImportIssueSeverityEnum(),
    )
    last_validation = graphene.Field(ImportValidationSummaryType)
    last_simulation = graphene.Field(ImportSimulationSummaryType)

    def resolve_status(self, info):
        value = _read_value(self, "status")
        return getattr(value, "value", value)

    def resolve_rows(self, info, page=1, per_page=100):
        if not isinstance(self, ImportBatch):
            return []
        start = max(0, (page - 1) * per_page)
        end = start + max(1, per_page)
        queryset = self.rows.all().order_by("row_number")[start:end]
        return list(queryset)

    def resolve_issues(self, info, page=1, per_page=200, severity=None):
        if not isinstance(self, ImportBatch):
            return []
        queryset = self.issues.all().order_by("row_number", "created_at")
        if severity:
            queryset = queryset.filter(severity=getattr(severity, "value", severity))
        start = max(0, (page - 1) * per_page)
        end = start + max(1, per_page)
        return list(queryset[start:end])

    def resolve_last_validation(self, info):
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "blocking_issues": self.invalid_rows,
            "warnings": 0,
        }

    def resolve_last_simulation(self, info):
        latest = self.simulation_snapshots.order_by("-executed_at").first()
        if not latest:
            return None
        return {
            "can_commit": latest.can_commit,
            "would_create": latest.would_create,
            "would_update": latest.would_update,
            "blocking_issues": latest.blocking_errors,
            "warnings": latest.warnings,
            "duration_ms": latest.duration_ms,
        }


class ModelImportBatchPageType(graphene.ObjectType):
    page = graphene.Int(required=True)
    per_page = graphene.Int(required=True)
    total = graphene.Int(required=True)
    results = graphene.List(graphene.NonNull(ModelImportBatchType), required=True)


class CreateModelImportBatchPayloadType(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    batch = graphene.Field(ModelImportBatchType)
    issues = graphene.List(graphene.NonNull(ImportIssueType), required=True)


class UpdateModelImportBatchPayloadType(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    batch = graphene.Field(ModelImportBatchType)
    rows = graphene.List(graphene.NonNull(ModelImportRowType), required=True)
    issues = graphene.List(graphene.NonNull(ImportIssueType), required=True)
    validation_summary = graphene.Field(ImportValidationSummaryType)
    simulation_summary = graphene.Field(ImportSimulationSummaryType)
    commit_summary = graphene.Field(ImportCommitSummaryType)


class DeleteModelImportBatchPayloadType(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    deleted_batch_id = graphene.ID()
