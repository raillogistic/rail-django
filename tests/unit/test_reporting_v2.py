import pytest
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from django.db import models
from django.db.models import Case, Value

from rail_django.extensions.reporting.types import ReportingError
from rail_django.extensions.reporting.utils import _safe_formula_eval, _safe_query_expression
from rail_django.extensions.reporting.visualization_registry import (
    get_visualization_type,
    get_available_types,
    register_visualization_type,
    VisualizationTypeConfig,
)
from rail_django.extensions.reporting.renderers import get_renderer, CsvRenderer, JsonRenderer
from rail_django.extensions.reporting.engine.data_sources import (
    OrmDataSourceAdapter,
    SqlDataSourceAdapter,
    PythonDataSourceAdapter,
)
from rail_django.extensions.reporting.services import ReportingService


@pytest.mark.unit
class TestFormulaEvaluator:
    def test_basic_arithmetic(self):
        ctx = {"a": 10, "b": 5}
        assert _safe_formula_eval("a + b * 2", ctx) == 20
        assert _safe_formula_eval("(a + b) * 2", ctx) == 30
        assert _safe_formula_eval("a / b", ctx) == 2.0
        assert _safe_formula_eval("a ** 2", ctx) == 100

    def test_builtins_if_coalesce(self):
        ctx = {"total": 100, "discount": None, "active": True}
        assert _safe_formula_eval("IF(active, total, 0)", ctx) == 100
        assert _safe_formula_eval("IF(not active, total, 0)", ctx) == 0
        assert _safe_formula_eval("COALESCE(discount, 10)", ctx) == 10
        assert _safe_formula_eval("COALESCE(total, 10)", ctx) == 100

    def test_builtins_math(self):
        ctx = {"val": -15.5}
        assert _safe_formula_eval("abs(val)", ctx) == 15.5
        assert _safe_formula_eval("round(val)", ctx) == -16
        assert _safe_formula_eval("max(10, 20, 5)", ctx) == 20

    def test_builtins_analytics(self):
        ctx = {"current": 150, "prev": 100}
        assert _safe_formula_eval("PCT_CHANGE(current, prev)", ctx) == 0.5
        assert _safe_formula_eval("PCT_CHANGE(current, 0)", ctx) is None

    def test_ternary_operator(self):
        ctx = {"status": "ok", "val": 10}
        assert _safe_formula_eval("val * 2 if status == 'ok' else 0", ctx) == 20
        assert _safe_formula_eval("val * 2 if status == 'err' else 0", ctx) == 0

    def test_invalid_call(self):
        ctx = {"val": 10}
        with pytest.raises(ReportingError):
            _safe_formula_eval("eval('import os')", ctx)


@pytest.mark.unit
class TestQueryExpressionEvaluator:
    def test_basic_arithmetic(self):
        allowed = {"revenue", "cost"}
        expr = _safe_query_expression("revenue - cost", allowed_names=allowed)
        assert expr.__class__.__name__ == "CombinedExpression"

    def test_builtins_orm(self):
        allowed = {"discount"}
        expr = _safe_query_expression("COALESCE(discount, 0)", allowed_names=allowed)
        assert expr.__class__.__name__ == "Coalesce"

    def test_ternary_orm(self):
        allowed = {"is_active", "amount"}
        expr = _safe_query_expression("amount if is_active else 0", allowed_names=allowed)
        assert expr.__class__.__name__ == "Case"


@pytest.mark.unit
class TestVisualizationRegistry:
    def test_builtin_types_loaded(self):
        types = get_available_types()
        assert len(types) >= 18
        assert get_visualization_type("table") is not None
        assert get_visualization_type("scatter") is not None

    def test_register_custom_type(self):
        config = VisualizationTypeConfig(
            name="test_viz",
            label="Test Viz",
            required_dimensions=1,
            required_metrics=2,
        )
        register_visualization_type(config)
        assert get_visualization_type("test_viz") == config


@pytest.mark.unit
class TestRenderers:
    def test_get_renderer(self):
        assert isinstance(get_renderer("csv"), CsvRenderer)
        assert isinstance(get_renderer("json"), JsonRenderer)
        with pytest.raises(ValueError):
            get_renderer("unknown_format")

    def test_csv_renderer(self):
        renderer = CsvRenderer()
        payload = {
            "columns": [{"name": "id", "label": "ID"}, {"name": "name", "label": "Nom"}],
            "rows": [{"id": 1, "name": "Test 1"}, {"id": 2, "name": "Test 2"}],
        }
        result = renderer.render(payload)
        assert b"ID,Nom" in result
        assert b"1,Test 1" in result

    def test_json_renderer(self):
        renderer = JsonRenderer()
        dt = datetime(2023, 1, 1, 12, 0)
        dec = Decimal("10.50")
        uid = uuid4()
        payload = {
            "rows": [{"id": 1, "date": dt, "amount": dec, "uid": uid, "tags": {"a", "b"}}]
        }
        result = renderer.render(payload)
        content = result.decode("utf-8")
        assert "2023-01-01T12:00:00" in content
        assert "10.5" in content
        assert str(uid) in content


@pytest.mark.unit
class TestDataSourceAdapters:
    def test_sql_adapter(self):
        adapter = SqlDataSourceAdapter({"sql": "SELECT 1 as val", "params": {}})
        assert adapter.sql == "SELECT 1 as val"
        assert adapter.supports_orm_operations() is False
        assert adapter.get_model_class() is None

    def test_python_adapter(self):
        def dummy_callable():
            return [{"id": 1}]
        
        # Test missing callable
        with pytest.raises(ReportingError):
            PythonDataSourceAdapter({})
            
        # We can't easily test dynamic import in unit test without a real module path
        # But we can test properties
        adapter = PythonDataSourceAdapter.__new__(PythonDataSourceAdapter)
        adapter.source_config = {}
        assert adapter.supports_orm_operations() is False

    @pytest.mark.django_db
    def test_orm_adapter(self):
        # Using the ReportingDataset model for the ORM adapter test
        adapter = OrmDataSourceAdapter({
            "app_label": "rail_django",
            "model_name": "reportingdataset",
        })
        assert adapter.supports_orm_operations() is True
        assert adapter.get_model_class().__name__ == "ReportingDataset"
        assert adapter.validate_field_path("code") is True
        assert adapter.validate_field_path("invalid_field") is False


@pytest.mark.unit
class TestServices:
    def test_get_available_formats(self):
        formats = ReportingService.get_available_export_formats()
        assert "csv" in formats
        assert "json" in formats

    def test_get_available_viz_types(self):
        types = ReportingService.get_available_visualization_types()
        assert any(t["name"] == "table" for t in types)
