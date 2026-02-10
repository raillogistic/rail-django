import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from types import SimpleNamespace

from rail_django.extensions.importing.schema.mutations import CreateModelImportBatchMutation
from rail_django.extensions.importing.services import resolve_template_descriptor
from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def auth_client():
    harness = build_schema(schema_name="test_import_upload_review", apps=["test_app"])
    user = get_user_model().objects.create_superuser(
        username="import_upload_admin",
        email="import_upload_admin@example.com",
        password="pass",
    )
    return RailGraphQLTestClient(
        harness.schema,
        schema_name="test_import_upload_review",
        user=user,
    )


@pytest.fixture
def anonymous_client():
    harness = build_schema(schema_name="test_import_upload_review_anon", apps=["test_app"])
    return RailGraphQLTestClient(harness.schema, schema_name="test_import_upload_review_anon")


TEMPLATE_QUERY = """
query Template($appLabel: String!, $modelName: String!) {
  modelImportTemplate(appLabel: $appLabel, modelName: $modelName) {
    templateId
    version
  }
}
"""

CREATE_MUTATION = """
mutation CreateBatch($input: CreateModelImportBatchInput!) {
  createModelImportBatch(input: $input) {
    ok
    batch {
      id
      status
      totalRows
      invalidRows
    }
    issues {
      code
      message
    }
  }
}
"""

CREATE_MUTATION_WITH_ISSUES = """
mutation CreateBatchWithIssues($input: CreateModelImportBatchInput!) {
  createModelImportBatch(input: $input) {
    ok
    batch {
      id
      status
      totalRows
      invalidRows
    }
    issues {
      id
      rowNumber
      fieldPath
      code
      severity
      message
      stage
    }
  }
}
"""

BATCH_PAGES_QUERY = """
query BatchPages($appLabel: String!, $modelName: String!, $perPage: Int!) {
  modelImportBatchPages(appLabel: $appLabel, modelName: $modelName, perPage: $perPage) {
    page
    perPage
    total
    results {
      id
      status
      totalRows
      invalidRows
    }
  }
}
"""

UPDATE_MUTATION = """
mutation UpdateBatch($input: UpdateModelImportBatchInput!) {
  updateModelImportBatch(input: $input) {
    ok
    batch {
      id
      status
      invalidRows
    }
    issues {
      id
      code
      severity
      fieldPath
      stage
      message
    }
  }
}
"""

FULL_BATCH_QUERY = """
query Batch($batchId: ID!) {
  modelImportBatch(batchId: $batchId) {
    id
    status
    rows(page: 1, perPage: 10) {
      id
      rowNumber
      action
      status
      issueCount
    }
    issues(page: 1, perPage: 20) {
      id
      severity
      code
    }
  }
}
"""


def _template(auth_client):
    result = auth_client.execute(
        TEMPLATE_QUERY,
        variables={"appLabel": "test_app", "modelName": "Product"},
    )
    assert result.get("errors") is None
    return result["data"]["modelImportTemplate"]


def _sample_csv():
    return "id,name,price,cost_price,inventory_count\n,Widget A,10.50,4.20,5\n,Widget B,12.00,5.00,7\n"


def test_create_model_import_batch_and_batch_pages_limit(auth_client):
    template = _template(auth_client)
    result = auth_client.execute(
        CREATE_MUTATION,
        variables={
            "input": {
                "appLabel": "test_app",
                "modelName": "Product",
                "templateId": template["templateId"],
                "templateVersion": template["version"],
                "file": _sample_csv(),
                "fileFormat": "CSV",
            }
        },
    )
    assert result.get("errors") is None
    payload = result["data"]["createModelImportBatch"]
    assert payload["ok"] is True
    assert payload["batch"]["id"]
    assert payload["batch"]["totalRows"] == 2
    batch_id = payload["batch"]["id"]

    detail = auth_client.execute(
        FULL_BATCH_QUERY,
        variables={"batchId": batch_id},
    )
    assert detail.get("errors") is None
    rows = detail["data"]["modelImportBatch"]["rows"]
    assert len(rows) == 2
    assert all(row["action"] in {"CREATE", "UPDATE"} for row in rows)
    assert all(row["status"] in {"VALID", "INVALID", "READY", "LOCKED", "COMMITTED"} for row in rows)

    pages = auth_client.execute(
        BATCH_PAGES_QUERY,
        variables={
            "appLabel": "test_app",
            "modelName": "Product",
            "perPage": 999,
        },
    )
    assert pages.get("errors") is None
    page_payload = pages["data"]["modelImportBatchPages"]
    assert page_payload["perPage"] == 200
    assert page_payload["total"] >= 1


def test_create_model_import_batch_rejects_wrong_template_version(auth_client):
    template = _template(auth_client)
    result = auth_client.execute(
        CREATE_MUTATION,
        variables={
            "input": {
                "appLabel": "test_app",
                "modelName": "Product",
                "templateId": template["templateId"],
                "templateVersion": "invalid-version",
                "file": _sample_csv(),
                "fileFormat": "CSV",
            }
        },
    )
    assert result.get("errors") is None
    payload = result["data"]["createModelImportBatch"]
    assert payload["ok"] is False
    assert any(issue["code"] == "TEMPLATE_VERSION_MISMATCH" for issue in payload["issues"])


def test_create_model_import_batch_invalid_field_returns_readable_issue_payload(auth_client):
    template = _template(auth_client)
    result = auth_client.execute(
        CREATE_MUTATION_WITH_ISSUES,
        variables={
            "input": {
                "appLabel": "test_app",
                "modelName": "Product",
                "templateId": template["templateId"],
                "templateVersion": template["version"],
                "file": (
                    "id,name,price,cost_price,inventory_count\n"
                    ",Widget A,not-a-number,4.20,5\n"
                ),
                "fileFormat": "CSV",
            }
        },
    )

    assert result.get("errors") is None
    payload = result["data"]["createModelImportBatch"]
    assert payload["batch"]["invalidRows"] >= 1
    assert payload["issues"]
    assert payload["issues"][0]["code"] == "INVALID_FIELD_VALUE"
    assert payload["issues"][0]["severity"] == "ERROR"
    assert payload["issues"][0]["fieldPath"] == "price"


def test_validate_action_uses_create_when_matching_key_target_is_missing(auth_client):
    template = _template(auth_client)
    create = auth_client.execute(
        CREATE_MUTATION,
        variables={
            "input": {
                "appLabel": "test_app",
                "modelName": "Product",
                "templateId": template["templateId"],
                "templateVersion": template["version"],
                "file": (
                    "id,name,price,cost_price,inventory_count\n"
                    "999999,Widget A,10.50,4.20,5\n"
                ),
                "fileFormat": "CSV",
            }
        },
    )
    assert create.get("errors") is None
    batch_id = create["data"]["createModelImportBatch"]["batch"]["id"]

    validate = auth_client.execute(
        UPDATE_MUTATION,
        variables={
            "input": {
                "batchId": batch_id,
                "action": "VALIDATE",
            }
        },
    )
    assert validate.get("errors") is None
    payload = validate["data"]["updateModelImportBatch"]
    assert payload is not None
    assert payload["issues"] is not None
    assert all(issue["code"] != "RECORD_NOT_FOUND" for issue in payload["issues"])

    detail = auth_client.execute(
        FULL_BATCH_QUERY,
        variables={"batchId": batch_id},
    )
    assert detail.get("errors") is None
    batch_payload = detail["data"]["modelImportBatch"]
    assert batch_payload is not None
    assert isinstance(batch_payload["issues"], list)
    assert batch_payload["rows"][0]["action"] == "CREATE"


def test_upload_and_batch_pages_require_authentication(anonymous_client):
    result = anonymous_client.execute(
        TEMPLATE_QUERY,
        variables={"appLabel": "test_app", "modelName": "Product"},
    )
    assert result.get("errors") is not None


def test_create_batch_mutation_recovers_uploaded_file_from_request_files():
    user = get_user_model().objects.create_superuser(
        username="import_upload_admin_fallback",
        email="import_upload_admin_fallback@example.com",
        password="pass",
    )
    descriptor = resolve_template_descriptor(app_label="test_app", model_name="Product")
    uploaded = SimpleUploadedFile(
        "products.csv",
        b"id,name,price,cost_price,inventory_count\n,Widget A,10.50,4.20,5\n",
    )
    info = SimpleNamespace(
        context=SimpleNamespace(
            user=user,
            FILES=MultiValueDict({"0": [uploaded]}),
        )
    )

    payload = CreateModelImportBatchMutation().mutate(
        info,
        {
            "app_label": "test_app",
            "model_name": "Product",
            "template_id": descriptor["template_id"],
            "template_version": descriptor["exact_version"],
            "file": {},
            "file_format": "CSV",
        },
    )

    assert payload["ok"] is True
    assert payload["batch"] is not None
    assert payload["batch"].total_rows == 1
