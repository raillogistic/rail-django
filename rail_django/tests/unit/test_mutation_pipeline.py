"""
Tests for the mutation pipeline architecture.

This module tests:
- MutationContext dataclass
- MutationStep base class and pipeline execution
- Individual pipeline steps
- PipelineBuilder configuration
- Mutation factories
- Integration with MutationGenerator
"""

from unittest.mock import MagicMock, Mock, patch
from dataclasses import asdict

import pytest
from django.test import TestCase

from rail_django.generators.pipeline.context import MutationContext
from rail_django.generators.pipeline.base import (
    MutationStep,
    MutationPipeline,
    ConditionalStep,
    OperationFilteredStep,
)
from rail_django.generators.pipeline.builder import PipelineBuilder
from rail_django.generators.pipeline.utils import (
    sanitize_input_data,
    normalize_enum_inputs,
    filter_read_only_fields,
    auto_populate_created_by,
    decode_global_id,
)


@pytest.mark.unit
class TestMutationContext:
    """Tests for MutationContext dataclass."""

    def test_context_creation(self):
        """Test basic context creation."""
        mock_info = Mock()
        mock_model = Mock()
        mock_model.__name__ = "TestModel"
        mock_model._meta = Mock()
        mock_model._meta.app_label = "test_app"
        mock_model._meta.model_name = "testmodel"

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={"name": "test"},
            input_data={"name": "test"},
        )

        assert ctx.operation == "create"
        assert ctx.model_name == "TestModel"
        assert ctx.app_label == "test_app"
        assert not ctx.should_abort
        assert len(ctx.errors) == 0

    def test_add_error_sets_abort(self):
        """Test that adding an error sets should_abort flag."""
        mock_info = Mock()
        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={},
            input_data={},
        )

        ctx.add_error("Something went wrong", field_name="name")

        assert ctx.should_abort
        assert len(ctx.errors) == 1
        assert ctx.errors[0].message == "Something went wrong"
        assert ctx.errors[0].field == "name"

    def test_add_warning_does_not_abort(self):
        """Test that adding a warning does not set should_abort flag."""
        mock_info = Mock()
        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={},
            input_data={},
        )

        ctx.add_warning("This is a warning")

        assert not ctx.should_abort
        assert len(ctx.errors) == 1

    def test_user_property(self):
        """Test user property accessor."""
        mock_info = Mock()
        mock_user = Mock()
        mock_info.context.user = mock_user
        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={},
            input_data={},
        )

        assert ctx.user == mock_user

    def test_get_permission_codename(self):
        """Test permission codename generation."""
        mock_info = Mock()
        mock_model = Mock()
        mock_model.__name__ = "TestModel"
        mock_model._meta = Mock()
        mock_model._meta.app_label = "myapp"
        mock_model._meta.model_name = "testmodel"

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={},
            input_data={},
        )

        assert ctx.get_permission_codename() == "myapp.add_testmodel"

        ctx.operation = "update"
        assert ctx.get_permission_codename() == "myapp.change_testmodel"

        ctx.operation = "delete"
        assert ctx.get_permission_codename() == "myapp.delete_testmodel"


@pytest.mark.unit
class TestMutationStep:
    """Tests for MutationStep base class."""

    def test_step_should_run_by_default(self):
        """Test that steps run by default when not aborted."""

        class TestStep(MutationStep):
            name = "test"

            def execute(self, ctx):
                return ctx

        step = TestStep()
        mock_ctx = Mock()
        mock_ctx.should_abort = False

        assert step.should_run(mock_ctx)

    def test_step_should_not_run_when_aborted(self):
        """Test that steps skip when context is aborted."""

        class TestStep(MutationStep):
            name = "test"

            def execute(self, ctx):
                return ctx

        step = TestStep()
        mock_ctx = Mock()
        mock_ctx.should_abort = True

        assert not step.should_run(mock_ctx)


@pytest.mark.unit
class TestMutationPipeline:
    """Tests for MutationPipeline orchestration."""

    def test_pipeline_executes_steps_in_order(self):
        """Test that pipeline executes steps in order."""
        execution_order = []

        class StepA(MutationStep):
            order = 20
            name = "step_a"

            def execute(self, ctx):
                execution_order.append("a")
                return ctx

        class StepB(MutationStep):
            order = 10
            name = "step_b"

            def execute(self, ctx):
                execution_order.append("b")
                return ctx

        class StepC(MutationStep):
            order = 30
            name = "step_c"

            def execute(self, ctx):
                execution_order.append("c")
                return ctx

        pipeline = MutationPipeline([StepA(), StepC(), StepB()])
        mock_ctx = Mock()
        mock_ctx.should_abort = False

        pipeline.execute(mock_ctx)

        assert execution_order == ["b", "a", "c"]

    def test_pipeline_stops_on_abort(self):
        """Test that pipeline stops when a step sets should_abort."""
        execution_order = []

        class StepA(MutationStep):
            order = 10
            name = "step_a"

            def execute(self, ctx):
                execution_order.append("a")
                ctx.should_abort = True
                return ctx

        class StepB(MutationStep):
            order = 20
            name = "step_b"

            def execute(self, ctx):
                execution_order.append("b")
                return ctx

        pipeline = MutationPipeline([StepA(), StepB()])
        mock_ctx = Mock()
        mock_ctx.should_abort = False

        pipeline.execute(mock_ctx)

        assert execution_order == ["a"]

    def test_get_step_names(self):
        """Test getting step names from pipeline."""

        class StepA(MutationStep):
            order = 10
            name = "step_a"

            def execute(self, ctx):
                return ctx

        class StepB(MutationStep):
            order = 20
            name = "step_b"

            def execute(self, ctx):
                return ctx

        pipeline = MutationPipeline([StepB(), StepA()])

        assert pipeline.get_step_names() == ["step_a", "step_b"]


@pytest.mark.unit
class TestConditionalStep:
    """Tests for ConditionalStep wrapper."""

    def test_conditional_step_runs_when_condition_true(self):
        """Test that conditional step runs when condition is true."""
        executed = []

        class InnerStep(MutationStep):
            name = "inner"

            def execute(self, ctx):
                executed.append(True)
                return ctx

        step = ConditionalStep(InnerStep(), condition=lambda ctx: True)
        mock_ctx = Mock()
        mock_ctx.should_abort = False

        assert step.should_run(mock_ctx)
        step.execute(mock_ctx)
        assert executed == [True]

    def test_conditional_step_skips_when_condition_false(self):
        """Test that conditional step skips when condition is false."""
        step = ConditionalStep(Mock(), condition=lambda ctx: False)
        mock_ctx = Mock()
        mock_ctx.should_abort = False

        assert not step.should_run(mock_ctx)


@pytest.mark.unit
class TestOperationFilteredStep:
    """Tests for OperationFilteredStep."""

    def test_operation_filtered_step_runs_for_allowed_operation(self):
        """Test that step runs for allowed operations."""

        class CreateOnlyStep(OperationFilteredStep):
            allowed_operations = ("create",)
            name = "create_only"

            def execute(self, ctx):
                return ctx

        step = CreateOnlyStep()
        mock_ctx = Mock()
        mock_ctx.should_abort = False
        mock_ctx.operation = "create"

        assert step.should_run(mock_ctx)

    def test_operation_filtered_step_skips_for_other_operation(self):
        """Test that step skips for non-allowed operations."""

        class CreateOnlyStep(OperationFilteredStep):
            allowed_operations = ("create",)
            name = "create_only"

            def execute(self, ctx):
                return ctx

        step = CreateOnlyStep()
        mock_ctx = Mock()
        mock_ctx.should_abort = False
        mock_ctx.operation = "update"

        assert not step.should_run(mock_ctx)


@pytest.mark.unit
class TestPipelineUtils:
    """Tests for pipeline utility functions."""

    def test_sanitize_input_data_handles_double_quotes(self):
        """Test that double quotes are properly escaped."""
        input_data = {"name": 'Test ""quoted"" value'}
        result = sanitize_input_data(input_data)
        assert result["name"] == 'Test "quoted" value'

    def test_sanitize_input_data_converts_id_to_string(self):
        """Test that ID is converted to string."""
        from uuid import UUID

        input_data = {"id": UUID("12345678-1234-5678-1234-567812345678")}
        result = sanitize_input_data(input_data)
        assert isinstance(result["id"], str)

    def test_sanitize_input_data_handles_nested(self):
        """Test that nested structures are sanitized."""
        input_data = {
            "items": [{"name": 'Test ""quote""'}],
            "nested": {"value": 'Another ""quote""'},
        }
        result = sanitize_input_data(input_data)
        assert result["items"][0]["name"] == 'Test "quote"'
        assert result["nested"]["value"] == 'Another "quote"'

    def test_normalize_enum_inputs(self):
        """Test that enum values are normalized."""

        class MockEnum:
            def __init__(self, value):
                self.value = value

        mock_model = Mock()
        mock_field = Mock()
        mock_field.name = "status"
        mock_field.choices = [("active", "Active"), ("inactive", "Inactive")]
        mock_model._meta.get_fields.return_value = [mock_field]

        input_data = {"status": MockEnum("active")}
        result = normalize_enum_inputs(input_data, mock_model)

        assert result["status"] == "active"

    def test_filter_read_only_fields(self):
        """Test that read-only fields are filtered out."""
        mock_meta = Mock()
        mock_meta.field_config.read_only = ["created_at", "updated_at"]

        input_data = {"name": "test", "created_at": "2024-01-01", "value": 100}
        result = filter_read_only_fields(input_data, mock_meta)

        assert "name" in result
        assert "value" in result
        assert "created_at" not in result

    def test_auto_populate_created_by(self):
        """Test auto-population of created_by field."""
        mock_model = Mock()
        mock_model._meta.get_field.return_value = Mock()

        mock_user = Mock()
        mock_user.is_authenticated = True
        mock_user.id = 123

        input_data = {"name": "test"}
        result = auto_populate_created_by(input_data, mock_model, mock_user)

        assert result["created_by"] == 123

    def test_auto_populate_created_by_skips_if_exists(self):
        """Test that created_by is not overwritten if already present."""
        mock_model = Mock()
        mock_user = Mock()
        mock_user.is_authenticated = True
        mock_user.id = 123

        input_data = {"name": "test", "created_by": 456}
        result = auto_populate_created_by(input_data, mock_model, mock_user)

        assert result["created_by"] == 456

    def test_decode_global_id(self):
        """Test decoding of GraphQL global IDs."""
        # Test with a non-encoded ID
        type_name, decoded_id = decode_global_id("123")
        assert decoded_id == "123"


@pytest.mark.unit
class TestPipelineBuilder:
    """Tests for PipelineBuilder."""

    def test_builder_creates_create_pipeline(self):
        """Test that builder creates a create pipeline."""
        builder = PipelineBuilder()
        mock_model = Mock()

        pipeline = builder.build_create_pipeline(mock_model)

        assert pipeline is not None
        step_names = pipeline.get_step_names()
        assert "authentication" in step_names
        assert "create_execution" in step_names

    def test_builder_creates_update_pipeline(self):
        """Test that builder creates an update pipeline."""
        builder = PipelineBuilder()
        mock_model = Mock()

        pipeline = builder.build_update_pipeline(mock_model)

        assert pipeline is not None
        step_names = pipeline.get_step_names()
        assert "instance_lookup" in step_names
        assert "update_execution" in step_names

    def test_builder_creates_delete_pipeline(self):
        """Test that builder creates a delete pipeline."""
        builder = PipelineBuilder()
        mock_model = Mock()

        pipeline = builder.build_delete_pipeline(mock_model)

        assert pipeline is not None
        step_names = pipeline.get_step_names()
        assert "instance_lookup" in step_names
        assert "delete_execution" in step_names

    def test_builder_skip_step(self):
        """Test that builder can skip specific steps."""
        builder = PipelineBuilder()
        builder.skip_step("audit")

        mock_model = Mock()
        pipeline = builder.build_create_pipeline(mock_model)

        step_names = pipeline.get_step_names()
        assert "audit" not in step_names

    def test_builder_add_custom_step(self):
        """Test that builder can add custom steps."""

        class CustomStep(MutationStep):
            order = 85
            name = "custom"

            def execute(self, ctx):
                return ctx

        builder = PipelineBuilder()
        builder.add_step(CustomStep())

        mock_model = Mock()
        pipeline = builder.build_create_pipeline(mock_model)

        step_names = pipeline.get_step_names()
        assert "custom" in step_names

    def test_builder_configure_authentication(self):
        """Test that builder can configure authentication requirement."""
        builder = PipelineBuilder()
        builder.require_authentication(False)

        mock_model = Mock()
        pipeline = builder.build_create_pipeline(mock_model)

        # The pipeline should still have the auth step, but it's configured to not require auth
        step_names = pipeline.get_step_names()
        assert "authentication" in step_names


@pytest.mark.unit
class TestPipelineSteps:
    """Tests for individual pipeline steps."""

    def test_authentication_step_allows_authenticated_user(self):
        """Test that authentication step allows authenticated users."""
        from rail_django.generators.pipeline.steps.authentication import (
            AuthenticationStep,
        )

        step = AuthenticationStep()

        mock_user = Mock()
        mock_user.is_authenticated = True

        mock_info = Mock()
        mock_info.context.user = mock_user

        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={},
            input_data={},
        )

        result = step.execute(ctx)

        assert not result.should_abort
        assert len(result.errors) == 0

    def test_authentication_step_blocks_anonymous_user(self):
        """Test that authentication step blocks anonymous users."""
        from rail_django.generators.pipeline.steps.authentication import (
            AuthenticationStep,
        )

        step = AuthenticationStep()

        mock_user = Mock()
        mock_user.is_authenticated = False

        mock_info = Mock()
        mock_info.context.user = mock_user

        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={},
            input_data={},
        )

        result = step.execute(ctx)

        assert result.should_abort
        assert len(result.errors) == 1
        assert "Authentication required" in result.errors[0].message

    def test_sanitization_step(self):
        """Test that sanitization step processes input."""
        from rail_django.generators.pipeline.steps.sanitization import (
            InputSanitizationStep,
        )

        step = InputSanitizationStep()

        mock_info = Mock()
        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={'name': 'Test ""value""'},
            input_data={'name': 'Test ""value""'},
        )

        result = step.execute(ctx)

        assert result.input_data["name"] == 'Test "value"'

    def test_enum_normalization_step(self):
        """Test that enum normalization step processes enums."""
        from rail_django.generators.pipeline.steps.normalization import (
            EnumNormalizationStep,
        )

        class MockEnum:
            def __init__(self, value):
                self.value = value

        step = EnumNormalizationStep()

        mock_info = Mock()
        mock_model = Mock()
        mock_model.__name__ = "TestModel"
        mock_field = Mock()
        mock_field.name = "status"
        mock_field.choices = [("active", "Active")]
        mock_model._meta.get_fields.return_value = [mock_field]

        ctx = MutationContext(
            info=mock_info,
            model=mock_model,
            operation="create",
            raw_input={"status": MockEnum("active")},
            input_data={"status": MockEnum("active")},
        )

        result = step.execute(ctx)

        assert result.input_data["status"] == "active"
