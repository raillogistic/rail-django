"""Import mutation root definitions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import graphene
from django.utils import timezone

from ..constants import ImportIssueCode
from ..models import ImportBatchStatus, ImportIssue, ImportIssueSeverity, ImportIssueStage
from ..services import (
    commit_batch,
    create_import_batch,
    generate_error_report,
    get_import_batch,
    log_import_event,
    parse_uploaded_file,
    patch_import_rows,
    recompute_batch_counters,
    require_import_access,
    resolve_template_descriptor,
    run_simulation,
    stage_parsed_rows,
    validate_dataset,
    validate_patched_rows,
)
from ..types import ImportRowPatch
from ..services.errors import ImportServiceError
from .types import (
    CreateModelImportBatchPayloadType,
    DeleteModelImportBatchPayloadType,
    ImportFileFormatEnum,
    UpdateModelImportBatchActionEnum,
    UpdateModelImportBatchPayloadType,
)

try:  # pragma: no cover - optional dependency
    from graphene_file_upload.scalars import Upload
except Exception:  # pragma: no cover - fallback when package is not installed
    class Upload(graphene.Scalar):
        """Fallback Upload scalar accepting raw values in tests."""

        @staticmethod
        def serialize(value):
            return value

        @staticmethod
        def parse_literal(node):
            return getattr(node, "value", None)

        @staticmethod
        def parse_value(value):
            return value


def _input_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _extract_file_from_mapping(value: Mapping[str, Any]) -> Any | None:
    candidate_keys = ("file", "originFileObj", "raw", "value")
    for key in candidate_keys:
        candidate = value.get(key)
        if hasattr(candidate, "read"):
            return candidate
    for candidate in value.values():
        if hasattr(candidate, "read"):
            return candidate
    return None


def _resolve_uploaded_file(raw_file: Any, context: Any) -> Any:
    if hasattr(raw_file, "read"):
        return raw_file

    if isinstance(raw_file, Mapping):
        nested = _extract_file_from_mapping(raw_file)
        if nested is not None:
            return nested

    request_files = getattr(context, "FILES", None)
    if request_files:
        if isinstance(raw_file, Mapping):
            for key in raw_file.keys():
                candidate = request_files.get(str(key))
                if hasattr(candidate, "read"):
                    return candidate
        first_candidate = next(iter(request_files.values()), None)
        if hasattr(first_candidate, "read"):
            return first_candidate

    return raw_file


def _coerce_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _issue_payload(
    *,
    code: str,
    message: str,
    severity: str = ImportIssueSeverity.ERROR,
    row_number: int | None = None,
    field_path: str | None = None,
    stage: str = ImportIssueStage.PARSE,
) -> dict[str, Any]:
    return {
        "id": f"virtual:{code}:{row_number or 0}",
        "row_number": row_number,
        "field_path": field_path,
        "code": code,
        "severity": severity,
        "message": message,
        "suggested_fix": None,
        "stage": stage,
    }


def _validation_summary(batch) -> dict[str, int]:
    warning_count = batch.issues.filter(severity=ImportIssueSeverity.WARNING).count()
    return {
        "total_rows": batch.total_rows,
        "valid_rows": batch.valid_rows,
        "invalid_rows": batch.invalid_rows,
        "blocking_issues": batch.invalid_rows,
        "warnings": warning_count,
    }


class ImportRowPatchInput(graphene.InputObjectType):
    row_number = graphene.Int(required=True)
    edited_values = graphene.JSONString(required=True)


class CreateModelImportBatchInput(graphene.InputObjectType):
    app_label = graphene.String(required=True)
    model_name = graphene.String(required=True)
    template_id = graphene.ID(required=True)
    template_version = graphene.String(required=True)
    file = Upload(required=True)
    file_format = ImportFileFormatEnum(required=True)


class UpdateModelImportBatchInput(graphene.InputObjectType):
    batch_id = graphene.ID(required=True)
    action = UpdateModelImportBatchActionEnum(required=True)
    patches = graphene.List(graphene.NonNull(ImportRowPatchInput))


class DeleteModelImportBatchInput(graphene.InputObjectType):
    batch_id = graphene.ID(required=True)


class CreateModelImportBatchMutation(graphene.Mutation):
    class Arguments:
        input = CreateModelImportBatchInput(required=True)

    Output = CreateModelImportBatchPayloadType

    def mutate(self, info, input):
        app_label = _input_get(input, "app_label")
        model_name = _input_get(input, "model_name")
        template_id = str(_input_get(input, "template_id"))
        template_version = _input_get(input, "template_version")
        file_format = _enum_value(_input_get(input, "file_format"))
        uploaded_file = _resolve_uploaded_file(_input_get(input, "file"), info.context)
        file_name = getattr(uploaded_file, "name", "upload")

        user = getattr(info.context, "user", None)
        user_id = require_import_access(user, app_label=app_label, model_name=model_name)
        descriptor = resolve_template_descriptor(app_label=app_label, model_name=model_name)
        expected_template_id = descriptor["template_id"]
        expected_version = descriptor["exact_version"]

        if template_id != expected_template_id:
            return {
                "ok": False,
                "batch": None,
                "issues": [
                    _issue_payload(
                        code=ImportIssueCode.TEMPLATE_VERSION_MISMATCH,
                        message=(
                            f"Template id '{template_id}' does not match active template "
                            f"'{expected_template_id}'."
                        ),
                    )
                ],
            }
        if str(template_version) != str(expected_version):
            return {
                "ok": False,
                "batch": None,
                "issues": [
                    _issue_payload(
                        code=ImportIssueCode.TEMPLATE_VERSION_MISMATCH,
                        message=(
                            f"Template version '{template_version}' does not match active "
                            f"version '{expected_version}'."
                        ),
                    )
                ],
            }

        batch = create_import_batch(
            app_label=app_label,
            model_name=model_name,
            template_id=str(template_id),
            template_version=str(template_version),
            uploaded_by_user_id=user_id,
            file_name=file_name,
            file_format=str(file_format),
        )
        issues_payload: list[Any] = []

        try:
            parsed_file = parse_uploaded_file(
                uploaded_file,
                file_format=str(file_format),
                max_rows=descriptor["max_rows"],
                max_file_size_bytes=descriptor["max_file_size_bytes"],
            )
            stage_parsed_rows(
                batch=batch,
                parsed_rows=parsed_file.rows,
                descriptor=descriptor,
            )
            recompute_batch_counters(batch)
            batch.status = (
                ImportBatchStatus.REVIEWING if batch.total_rows > 0 else ImportBatchStatus.PARSED
            )
            batch.save(update_fields=["status", "updated_at"])
            if batch.invalid_rows > 0:
                generate_error_report(batch)
                issues_payload = list(batch.issues.all().order_by("row_number", "created_at"))
        except ImportServiceError as exc:
            issue = ImportIssue.objects.create(
                batch=batch,
                row_number=exc.row_number,
                field_path=exc.field_path,
                code=exc.code,
                severity=ImportIssueSeverity.ERROR,
                message=exc.message,
                stage=ImportIssueStage.PARSE,
            )
            batch.status = ImportBatchStatus.FAILED
            batch.save(update_fields=["status", "updated_at"])
            issues_payload = [issue]

        log_import_event(
            "create_batch",
            user_id=user_id,
            batch_id=str(batch.id),
            details={
                "app_label": app_label,
                "model_name": model_name,
                "file_name": file_name,
                "file_format": str(file_format),
                "total_rows": batch.total_rows,
                "invalid_rows": batch.invalid_rows,
            },
            kpis={
                "total_rows": batch.total_rows,
                "invalid_rows": batch.invalid_rows,
                "valid_rows": batch.valid_rows,
            },
        )
        return {"ok": batch.status != ImportBatchStatus.FAILED, "batch": batch, "issues": issues_payload}


class UpdateModelImportBatchMutation(graphene.Mutation):
    class Arguments:
        input = UpdateModelImportBatchInput(required=True)

    Output = UpdateModelImportBatchPayloadType

    def mutate(self, info, input):
        batch_id = _input_get(input, "batch_id")
        action = str(_enum_value(_input_get(input, "action")))
        patches_input = _input_get(input, "patches", []) or []

        batch = get_import_batch(batch_id)
        if batch is None:
            return {"ok": False, "batch": None, "rows": [], "issues": []}

        user = getattr(info.context, "user", None)
        user_id = require_import_access(
            user, app_label=batch.app_label, model_name=batch.model_name
        )

        descriptor = resolve_template_descriptor(
            app_label=batch.app_label, model_name=batch.model_name
        )
        touched_rows = []
        validation_summary = None
        simulation_summary = None
        commit_summary = None

        if action == "PATCH_ROWS":
            patches: list[ImportRowPatch] = [
                {
                    "row_number": int(_input_get(patch, "row_number")),
                    "edited_values": _coerce_json(_input_get(patch, "edited_values", {})),
                }
                for patch in patches_input
            ]
            touched_rows = patch_import_rows(batch, patches)
            validate_patched_rows(
                batch=batch,
                descriptor=descriptor,
                row_numbers=[row.row_number for row in touched_rows],
            )
            recompute_batch_counters(batch)
            validation_summary = _validation_summary(batch)
            if batch.invalid_rows > 0:
                generate_error_report(batch)
        elif action == "VALIDATE":
            validate_dataset(batch=batch, descriptor=descriptor)
            validation_summary = _validation_summary(batch)
            if batch.invalid_rows > 0:
                generate_error_report(batch)
        elif action == "SIMULATE":
            simulation_summary = run_simulation(batch)
            if not simulation_summary["can_commit"]:
                generate_error_report(batch)
        elif action == "COMMIT":
            latest_snapshot = batch.simulation_snapshots.order_by("-executed_at").first()
            latest_row_update = batch.rows.order_by("-updated_at").values_list("updated_at", flat=True).first()
            if latest_snapshot is None or not latest_snapshot.can_commit:
                return {
                    "ok": False,
                    "batch": batch,
                    "rows": [],
                    "issues": [
                        _issue_payload(
                            code=ImportIssueCode.UNKNOWN_ERROR,
                            message="Batch must be simulated successfully before commit.",
                            stage=ImportIssueStage.COMMIT,
                        )
                    ],
                }
            if latest_row_update and latest_row_update > latest_snapshot.executed_at:
                return {
                    "ok": False,
                    "batch": batch,
                    "rows": [],
                    "issues": [
                        _issue_payload(
                            code=ImportIssueCode.UNKNOWN_ERROR,
                            message="Batch has changed since the last simulation.",
                            stage=ImportIssueStage.COMMIT,
                        )
                    ],
                }
            try:
                commit_summary = commit_batch(batch=batch, descriptor=descriptor)
            except ImportServiceError as exc:
                issue = ImportIssue.objects.create(
                    batch=batch,
                    row_number=exc.row_number,
                    field_path=exc.field_path,
                    code=exc.code,
                    severity=ImportIssueSeverity.ERROR,
                    message=exc.message,
                    stage=ImportIssueStage.COMMIT,
                )
                batch.status = ImportBatchStatus.FAILED
                batch.save(update_fields=["status", "updated_at"])
                generate_error_report(batch)
                return {
                    "ok": False,
                    "batch": batch,
                    "rows": [],
                    "issues": [issue],
                }
        else:
            return {"ok": False, "batch": batch, "rows": [], "issues": []}

        log_import_event(
            "update_batch",
            user_id=user_id,
            batch_id=str(batch.id),
            details={
                "action": action,
                "status": batch.status,
                "total_rows": batch.total_rows,
                "invalid_rows": batch.invalid_rows,
                "committed_rows": batch.committed_rows,
            },
            kpis={
                "total_rows": batch.total_rows,
                "valid_rows": batch.valid_rows,
                "invalid_rows": batch.invalid_rows,
                "committed_rows": batch.committed_rows,
            },
        )

        return {
            "ok": True,
            "batch": batch,
            "rows": touched_rows,
            "issues": list(batch.issues.all().order_by("row_number", "created_at")),
            "validation_summary": validation_summary,
            "simulation_summary": simulation_summary,
            "commit_summary": commit_summary,
        }


class DeleteModelImportBatchMutation(graphene.Mutation):
    class Arguments:
        input = DeleteModelImportBatchInput(required=True)

    Output = DeleteModelImportBatchPayloadType

    def mutate(self, info, input):
        batch_id = _input_get(input, "batch_id")
        batch = get_import_batch(batch_id)
        if batch is None:
            return {"ok": False, "deleted_batch_id": None}

        user = getattr(info.context, "user", None)
        user_id = require_import_access(
            user, app_label=batch.app_label, model_name=batch.model_name
        )
        deleted_batch_id = str(batch.id)
        batch.delete()
        log_import_event(
            "delete_batch",
            user_id=user_id,
            batch_id=deleted_batch_id,
            details={"deleted_at": timezone.now().isoformat()},
            kpis={"deleted": True},
        )
        return {"ok": True, "deleted_batch_id": deleted_batch_id}


class ImportMutations(graphene.ObjectType):
    create_model_import_batch = CreateModelImportBatchMutation.Field()
    update_model_import_batch = UpdateModelImportBatchMutation.Field()
    delete_model_import_batch = DeleteModelImportBatchMutation.Field()
