import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_reporting_imports_with_framework_settings_even_without_optional_aggregates():
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "rail_django.config.framework_settings"

    command = [
        sys.executable,
        "-c",
        (
            "import django; "
            "django.setup(); "
            "import rail_django.extensions.reporting as reporting; "
            "assert reporting.DatasetExecutionEngine.__name__ == 'DatasetExecutionEngine'; "
            "print('ok')"
        ),
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_query_builder_reports_missing_optional_bit_xor(monkeypatch):
    from rail_django.extensions.reporting import ReportingError
    from rail_django.extensions.reporting.engine import query_builder
    from rail_django.extensions.reporting.engine.query_builder import QueryBuilderMixin

    class _DummyQueryBuilder(QueryBuilderMixin):
        pass

    builder = _DummyQueryBuilder()
    monkeypatch.setattr(
        query_builder,
        "connection",
        SimpleNamespace(vendor="postgresql"),
    )
    monkeypatch.delattr(query_builder.postgres_aggregates, "BitXor", raising=False)

    with pytest.raises(ReportingError, match="bit_xor"):
        builder._build_postgres_aggregation(
            "bit_xor",
            "flags",
            filter_q=None,
            options=None,
        )


def test_postgres_engine_reports_missing_optional_percentile(monkeypatch):
    from rail_django.extensions.reporting import MetricSpec, ReportingError
    from rail_django.extensions.reporting.engine import postgres_engine
    from rail_django.extensions.reporting.engine.postgres_engine import (
        PostgresDatasetExecutionEngine,
    )

    class _DummyPostgresEngine(PostgresDatasetExecutionEngine):
        def __init__(self):
            pass

        def _compile_filter_tree(
            self, raw_filters, *, quick_search, allowed_fields=None
        ):
            return None, [], []

    engine = _DummyPostgresEngine()
    monkeypatch.delattr(
        postgres_engine.postgres_aggregates,
        "PercentileCont",
        raising=False,
    )

    with pytest.raises(ReportingError, match="percentile"):
        engine._build_annotations(
            [
                MetricSpec(
                    name="p95_latency",
                    field="latency_ms",
                    aggregation="percentile:0.95",
                )
            ]
        )
