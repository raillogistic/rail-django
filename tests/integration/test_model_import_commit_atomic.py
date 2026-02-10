import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def auth_client():
    harness = build_schema(schema_name="test_import_commit", apps=["test_app"])
    user = get_user_model().objects.create_superuser(
        username="import_commit_admin",
        email="import_commit_admin@example.com",
        password="pass",
    )
    return RailGraphQLTestClient(harness.schema, schema_name="test_import_commit", user=user)


@pytest.fixture
def anonymous_client():
    harness = build_schema(schema_name="test_import_commit_anon", apps=["test_app"])
    return RailGraphQLTestClient(harness.schema, schema_name="test_import_commit_anon")


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
    batch { id status totalRows invalidRows }
    issues { code message }
  }
}
"""

UPDATE_MUTATION = """
mutation UpdateBatch($input: UpdateModelImportBatchInput!) {
  updateModelImportBatch(input: $input) {
    ok
    batch { id status committedRows totalRows invalidRows }
    issues { code message }
    validationSummary { totalRows validRows invalidRows blockingIssues warnings }
    simulationSummary { canCommit wouldCreate wouldUpdate blockingIssues warnings durationMs }
    commitSummary { totalRows committedRows createRows updateRows skippedRows }
  }
}
"""

DELETE_MUTATION = """
mutation DeleteBatch($input: DeleteModelImportBatchInput!) {
  deleteModelImportBatch(input: $input) {
    ok
    deletedBatchId
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


def _create_batch(auth_client, csv_content: str):
    template = _template(auth_client)
    result = auth_client.execute(
        CREATE_MUTATION,
        variables={
            "input": {
                "appLabel": "test_app",
                "modelName": "Product",
                "templateId": template["templateId"],
                "templateVersion": template["version"],
                "file": csv_content,
                "fileFormat": "CSV",
            }
        },
    )
    assert result.get("errors") is None
    payload = result["data"]["createModelImportBatch"]
    assert payload["batch"] is not None
    return payload["batch"]["id"]


def _run_action(auth_client, batch_id: str, action: str):
    result = auth_client.execute(
        UPDATE_MUTATION,
        variables={"input": {"batchId": batch_id, "action": action}},
    )
    assert result.get("errors") is None
    return result["data"]["updateModelImportBatch"]


def test_commit_flow_is_atomic_for_failing_and_passing_batches(auth_client):
    initial_count = Product.objects.count()

    failing_batch = _create_batch(
        auth_client,
        "id,name,price,cost_price,inventory_count\n,,10.00,2.00,3\n",
    )
    failing_validate = _run_action(auth_client, failing_batch, "VALIDATE")
    assert failing_validate["batch"]["status"] in {"VALIDATION_FAILED", "VALIDATIONFAILED"}
    failing_simulate = _run_action(auth_client, failing_batch, "SIMULATE")
    assert failing_simulate["simulationSummary"]["canCommit"] is False
    failing_commit = _run_action(auth_client, failing_batch, "COMMIT")
    assert failing_commit["ok"] is False
    assert Product.objects.count() == initial_count

    passing_batch = _create_batch(
        auth_client,
        "id,name,price,cost_price,inventory_count\n,Atomic A,15.00,4.00,8\n,Atomic B,18.00,6.00,9\n",
    )
    passing_validate = _run_action(auth_client, passing_batch, "VALIDATE")
    assert passing_validate["ok"] is True
    passing_simulate = _run_action(auth_client, passing_batch, "SIMULATE")
    assert passing_simulate["simulationSummary"]["canCommit"] is True
    passing_commit = _run_action(auth_client, passing_batch, "COMMIT")
    assert passing_commit["ok"] is True
    assert passing_commit["commitSummary"]["committedRows"] == 2
    assert Product.objects.count() == initial_count + 2


def test_delete_model_import_batch_requires_auth_and_deletes_batch(auth_client, anonymous_client):
    batch_id = _create_batch(
        auth_client,
        "id,name,price,cost_price,inventory_count\n,Delete Me,10.00,2.00,1\n",
    )
    unauthorized = anonymous_client.execute(
        DELETE_MUTATION,
        variables={"input": {"batchId": batch_id}},
    )
    assert unauthorized.get("errors") is not None

    authorized = auth_client.execute(
        DELETE_MUTATION,
        variables={"input": {"batchId": batch_id}},
    )
    assert authorized.get("errors") is None
    assert authorized["data"]["deleteModelImportBatch"]["ok"] is True
