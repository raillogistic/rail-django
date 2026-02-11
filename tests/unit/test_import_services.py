import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from rail_django.extensions.importing.models import (
    ImportBatch,
    ImportIssueSeverity,
)
from rail_django.extensions.importing.services import (
    commit_batch,
    create_import_batch,
    parse_uploaded_file,
    resolve_template_descriptor,
    run_simulation,
    stage_parsed_rows,
    validate_dataset,
)
from test_app.models import Category, Product

try:
    from openpyxl import Workbook
except Exception:  # pragma: no cover - optional dependency
    Workbook = None

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _make_batch() -> ImportBatch:
    return create_import_batch(
        app_label="test_app",
        model_name="Product",
        template_id="test_app.Product",
        template_version="v1",
        uploaded_by_user_id="1",
        file_name="products.csv",
        file_format="CSV",
    )


def test_parse_uploaded_file_handles_utf8_sig_and_latin1():
    utf8_content = "\ufeffid,name,price,cost_price,inventory_count\n,Équipement,10.5,2.0,1\n"
    parsed_utf8 = parse_uploaded_file(
        SimpleUploadedFile("utf8.csv", utf8_content.encode("utf-8")),
        file_format="CSV",
        max_rows=100,
        max_file_size_bytes=1024 * 1024,
    )
    assert parsed_utf8.rows[0]["name"] == "Équipement"

    latin_content = "id,name,price,cost_price,inventory_count\n,Matériel,12.0,3.0,2\n"
    parsed_latin = parse_uploaded_file(
        SimpleUploadedFile("latin.csv", latin_content.encode("latin-1")),
        file_format="CSV",
        max_rows=100,
        max_file_size_bytes=1024 * 1024,
    )
    assert parsed_latin.rows[0]["name"] == "Matériel"


def test_dataset_validator_flags_duplicate_matching_keys():
    descriptor = resolve_template_descriptor("test_app", "Product")
    batch = _make_batch()
    stage_parsed_rows(
        batch=batch,
        descriptor=descriptor,
        parsed_rows=[
            {"id": "100", "name": "Row A", "price": "10.00", "cost_price": "2.00", "inventory_count": "1"},
            {"id": "100", "name": "Row B", "price": "11.00", "cost_price": "2.50", "inventory_count": "2"},
        ],
    )

    issues = validate_dataset(batch=batch, descriptor=descriptor)
    assert any(issue.code == "DUPLICATE_MATCHING_KEY" for issue in issues)
    assert batch.issues.filter(code="DUPLICATE_MATCHING_KEY").count() == 2


def test_simulation_summary_blocks_commit_when_errors_exist():
    descriptor = resolve_template_descriptor("test_app", "Product")
    batch = _make_batch()
    stage_parsed_rows(
        batch=batch,
        descriptor=descriptor,
        parsed_rows=[{"id": "", "name": "", "price": "10.00", "cost_price": "2.00", "inventory_count": "1"}],
    )
    summary = run_simulation(batch)
    assert summary["can_commit"] is False
    assert summary["blocking_issues"] >= 1


def test_simulation_summary_allows_commit_for_valid_rows():
    descriptor = resolve_template_descriptor("test_app", "Product")
    batch = _make_batch()
    stage_parsed_rows(
        batch=batch,
        descriptor=descriptor,
        parsed_rows=[
            {"id": "", "name": "Good A", "price": "10.00", "cost_price": "2.00", "inventory_count": "1"},
            {"id": "", "name": "Good B", "price": "12.00", "cost_price": "3.00", "inventory_count": "2"},
        ],
    )

    # Drop warnings/errors if any were generated unexpectedly.
    batch.issues.filter(severity=ImportIssueSeverity.ERROR).delete()
    summary = run_simulation(batch)
    assert summary["can_commit"] is True
    assert summary["would_create"] == 2


def test_stage_parsed_rows_marks_update_when_matching_target_exists():
    descriptor = resolve_template_descriptor("test_app", "Product")
    existing = Product.objects.create(
        name="Existing Product",
        price="9.50",
        cost_price="4.00",
        inventory_count=3,
    )
    batch = _make_batch()

    stage_parsed_rows(
        batch=batch,
        descriptor=descriptor,
        parsed_rows=[
            {
                "id": str(existing.pk),
                "name": "Updated Name",
                "price": "10.00",
                "cost_price": "4.00",
                "inventory_count": "5",
            }
        ],
    )

    row = batch.rows.get(row_number=2)
    assert row.action == "UPDATE"
    assert row.target_record_id == str(existing.pk)


def test_stage_parsed_rows_keeps_create_when_matching_target_missing():
    descriptor = resolve_template_descriptor("test_app", "Product")
    batch = _make_batch()

    stage_parsed_rows(
        batch=batch,
        descriptor=descriptor,
        parsed_rows=[
            {
                "id": "999999",
                "name": "New Product",
                "price": "10.00",
                "cost_price": "4.00",
                "inventory_count": "5",
            }
        ],
    )

    row = batch.rows.get(row_number=2)
    assert row.action == "CREATE"
    assert row.target_record_id is None


def test_commit_batch_accepts_foreign_key_value_from_import_payload():
    descriptor = resolve_template_descriptor("test_app", "Product")
    category = Category.objects.create(name="Hardware")
    batch = _make_batch()
    stage_parsed_rows(
        batch=batch,
        descriptor=descriptor,
        parsed_rows=[
            {
                "id": "",
                "name": "FK Product",
                "price": "10.00",
                "cost_price": "2.00",
                "inventory_count": "1",
                "category": str(category.pk),
            }
        ],
    )

    validate_dataset(batch=batch, descriptor=descriptor)
    summary = run_simulation(batch)
    assert summary["can_commit"] is True

    commit_summary = commit_batch(batch=batch, descriptor=descriptor)
    assert commit_summary["committed_rows"] == 1
    created = Product.objects.get(name="FK Product")
    assert created.category_id == category.pk


def test_stage_parsed_rows_accepts_foreign_key_id_alias_column():
    descriptor = resolve_template_descriptor("test_app", "Product")
    category = Category.objects.create(name="Components")
    batch = _make_batch()
    stage_parsed_rows(
        batch=batch,
        descriptor=descriptor,
        parsed_rows=[
            {
                "id": "",
                "name": "Alias Product",
                "price": "11.00",
                "cost_price": "3.00",
                "inventory_count": "2",
                "category_id": str(category.pk),
            }
        ],
    )

    row = batch.rows.get(row_number=2)
    assert str(row.normalized_values["category"]) == str(category.pk)


def test_commit_uses_model_default_when_optional_non_null_field_is_blank():
    descriptor = resolve_template_descriptor("test_app", "Product")
    batch = _make_batch()
    stage_parsed_rows(
        batch=batch,
        descriptor=descriptor,
        parsed_rows=[
            {
                "id": "",
                "name": "Default Inventory Product",
                "price": "20.00",
                "cost_price": "7.00",
                "inventory_count": "",
            }
        ],
    )

    validate_dataset(batch=batch, descriptor=descriptor)
    summary = run_simulation(batch)
    assert summary["can_commit"] is True

    commit_summary = commit_batch(batch=batch, descriptor=descriptor)
    assert commit_summary["committed_rows"] == 1
    created = Product.objects.get(name="Default Inventory Product")
    assert created.inventory_count == 0


@pytest.mark.skipif(Workbook is None, reason="openpyxl is required for XLSX parsing")
def test_parse_uploaded_file_xlsx_keeps_alignment_with_blank_leading_header():
    import io

    workbook = Workbook()
    sheet = workbook.active
    sheet.append([" ", "reference", "name", "price"])
    sheet.append(["IGNORED", "REF-001", "Widget A", 10.5])

    buffer = io.BytesIO()
    workbook.save(buffer)
    xlsx_content = buffer.getvalue()

    parsed = parse_uploaded_file(
        SimpleUploadedFile("products.xlsx", xlsx_content),
        file_format="XLSX",
        max_rows=100,
        max_file_size_bytes=5 * 1024 * 1024,
    )

    assert parsed.headers == ["reference", "name", "price"]
    assert parsed.rows[0]["reference"] == "REF-001"
    assert parsed.rows[0]["name"] == "Widget A"
