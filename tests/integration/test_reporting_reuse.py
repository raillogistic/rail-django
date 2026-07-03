"""Integration coverage for reusable reporting catalogs and runtime access."""

from types import SimpleNamespace

import graphene
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from graphql import GraphQLError

from rail_django.extensions.reporting import (
    ReportingDataset,
    ReportingMutation,
    ReportingQuery,
    ReportingReport,
    ReportingService,
    ReportingStudioService,
)
from rail_django.extensions.reporting.security import (
    dataset_is_visible_to_user,
    report_is_visible_to_user,
)
from rail_django.extensions.reporting.types import ReportingError

pytestmark = pytest.mark.django_db


def catalog():
    datasets = [
        {
            "code": "orders",
            "title": "Orders",
            "source_app_label": "rail_django",
            "source_model": "ReportingDataset",
            "dimensions": [{"name": "id", "field": "id", "label": "ID"}],
            "metrics": [{"name": "count", "field": "id", "aggregation": "count"}],
            "allowed_roles": ["analyst"],
            "metadata": {"record_fields": ["id"]},
        }
    ]
    visualizations = [
        {
            "code": "orders_table",
            "title": "Orders",
            "dataset_code": "orders",
            "kind": "table",
            "config": {"query": {"mode": "records", "fields": ["id"]}},
        }
    ]
    reports = [
        {
            "code": "orders_report",
            "title": "Orders",
            "allowed_roles": ["analyst"],
            "filters": [
                {
                    "name": "record_id",
                    "field": "id",
                    "lookup": "exact",
                    "targets": [
                        {"datasetCode": "orders", "field": "id", "lookup": "exact"}
                    ],
                }
            ],
            "blocks": [{"visualization_code": "orders_table", "position": 1}],
        }
    ]
    return datasets, visualizations, reports


def analyst():
    user = get_user_model().objects.create_user(username="analyst")
    group, _ = Group.objects.get_or_create(name="analyst")
    user.groups.add(group)
    return user


def test_catalog_sync_is_safe_by_default_and_overwrites_explicitly():
    definitions = catalog()
    created = ReportingService.sync_catalog(*definitions)
    assert created["reports"]["created"] == 1
    definitions[0][0]["title"] = "Changed"
    skipped = ReportingService.sync_catalog(*definitions)
    assert skipped["datasets"]["skipped"] == 1
    assert ReportingDataset.objects.get(code="orders").title == "Orders"
    ReportingService.sync_catalog(*definitions, overwrite=True)
    assert ReportingDataset.objects.get(code="orders").title == "Changed"


def test_visibility_and_multi_dataset_filter_allowlist():
    ReportingService.sync_catalog(*catalog())
    report = ReportingReport.objects.get(code="orders_report")
    user = analyst()
    context = SimpleNamespace(user=user)
    assert dataset_is_visible_to_user(report.blocks.first().visualization.dataset, user)
    assert report_is_visible_to_user(report, user)
    payload = ReportingService.build_report_payload(
        context, report.code, filters={"record_id": 1}
    )
    assert (
        payload["visualizations"][0]["dataset"]["applied_filters"][0]["field"] == "id"
    )
    with pytest.raises(GraphQLError):
        ReportingService.build_report_payload(
            context, report.code, filters={"raw_orm_path": "blocked"}
        )


def test_studio_rejects_unsafe_paths_and_protects_catalog_assets(settings):
    settings.RAIL_DJANGO_REPORTING = {"author_roles": ["report_author"]}
    user = get_user_model().objects.create_superuser(
        username="studio-admin", email="studio@example.test", password="secret"
    )
    studio = ReportingStudioService(SimpleNamespace(user=user))
    data = {
        "title": "Safe",
        "source_app_label": "rail_django",
        "source_model": "ReportingDataset",
        "dimensions": [{"name": "id", "field": "id", "label": "ID"}],
        "metrics": [],
        "record_fields": ["missing__secret"],
    }
    with pytest.raises(ReportingError):
        studio.build_dataset(data)
    ReportingService.sync_catalog(*catalog())
    with pytest.raises(ReportingError):
        studio.delete_dataset(ReportingDataset.objects.get(code="orders").pk)


def test_generic_graphql_runtime_returns_objects():
    ReportingService.sync_catalog(*catalog())
    user = analyst()
    schema = graphene.Schema(query=ReportingQuery, mutation=ReportingMutation)
    result = schema.execute(
        "query { reportingReportList }",
        context_value=SimpleNamespace(user=user),
    )
    assert not result.errors
    assert result.data["reportingReportList"][0]["code"] == "orders_report"
