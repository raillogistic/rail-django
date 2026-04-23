from pathlib import Path

import pytest
from django.db import IntegrityError

from rail_django.extensions.async_jobs import resolve_managed_job_file
from rail_django.generators.mutations.errors import build_integrity_errors

pytestmark = pytest.mark.unit


class _FakeMeta:
    app_label = "tests"
    model_name = "fake_model"
    label = "tests.FakeModel"

    @staticmethod
    def get_fields():
        return []

    @staticmethod
    def get_field(_field_name):
        raise LookupError


class _FakeModel:
    __name__ = "FakeModel"
    _meta = _FakeMeta()


def test_resolve_managed_job_file_allows_files_under_storage_root(tmp_path):
    storage_dir = tmp_path / "managed"
    storage_dir.mkdir()
    managed_file = storage_dir / "artifact.csv"
    managed_file.write_text("ok", encoding="utf-8")

    resolved = resolve_managed_job_file(str(managed_file), storage_dir=storage_dir)

    assert resolved == managed_file.resolve()


def test_resolve_managed_job_file_rejects_files_outside_storage_root(tmp_path):
    storage_dir = tmp_path / "managed"
    storage_dir.mkdir()
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")

    resolved = resolve_managed_job_file(str(outside_file), storage_dir=storage_dir)

    assert resolved is None


def test_build_integrity_errors_hides_raw_database_details():
    error = IntegrityError(
        "psycopg2.errors.InternalError_: duplicate key at /var/lib/postgresql/data"
    )

    errors = build_integrity_errors(_FakeModel, error)

    assert len(errors) == 1
    assert errors[0].code == "INTEGRITY_ERROR"
    assert errors[0].message == "Database integrity error."
