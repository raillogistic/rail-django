"""
Unit tests for RelationInputTypeGenerator.

Tests unified relation input type generation (connect/create/update/disconnect/set).
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

import graphene

pytestmark = pytest.mark.unit


class TestRelationInputTypeGenerator:
    """Tests for RelationInputTypeGenerator class."""

    def test_generator_initialization(self):
        """Generator should initialize with type generator reference."""
        from rail_django.generators.types.relations import RelationInputTypeGenerator

        mock_type_gen = MagicMock()
        generator = RelationInputTypeGenerator(mock_type_gen)

        assert generator.type_generator is mock_type_gen
        assert isinstance(generator._registry, dict)
        assert len(generator._registry) == 0

    def test_generate_fk_relation_input_type(self):
        """Should generate relation input type for FK with singular unified operations."""
        from rail_django.generators.types.relations import RelationInputTypeGenerator

        mock_type_gen = MagicMock()
        mock_type_gen.mutation_settings.relation_max_nesting_depth = 3
        mock_type_gen.generate_input_type.return_value = type(
            "MockInput", (graphene.InputObjectType,), {}
        )

        generator = RelationInputTypeGenerator(mock_type_gen)

        mock_model = MagicMock()
        mock_model._meta.label_lower = "test_app.author"
        mock_model._meta.model_name = "author"
        mock_model.__name__ = "Author"

        mock_parent = MagicMock()
        mock_parent._meta.model_name = "post"
        mock_parent.__name__ = "Post"

        result = generator.generate_relation_input_type(
            related_model=mock_model,
            relation_type="fk",
            parent_model=mock_parent,
            depth=0,
        )

        # Should return an InputObjectType class
        assert issubclass(result, graphene.InputObjectType)
        # Should have connect/create/update fields
        assert "connect" in result._meta.fields
        assert "create" in result._meta.fields
        assert "update" in result._meta.fields
        # Singular inputs also expose disconnect and set
        assert "disconnect" in result._meta.fields
        assert "set" in result._meta.fields

    def test_generate_m2m_relation_input_type(self):
        """Should generate relation input type for M2M with list operations."""
        from rail_django.generators.types.relations import RelationInputTypeGenerator

        mock_type_gen = MagicMock()
        mock_type_gen.mutation_settings.relation_max_nesting_depth = 3
        mock_type_gen.generate_input_type.return_value = type(
            "MockInput", (graphene.InputObjectType,), {}
        )

        generator = RelationInputTypeGenerator(mock_type_gen)

        mock_model = MagicMock()
        mock_model._meta.label_lower = "test_app.tag"
        mock_model._meta.model_name = "tag"
        mock_model.__name__ = "Tag"

        result = generator.generate_relation_input_type(
            related_model=mock_model,
            relation_type="m2m",
            parent_model=None,
            depth=0,
        )

        # Should return an InputObjectType class
        assert issubclass(result, graphene.InputObjectType)
        # Should have all operation fields for M2M
        assert "connect" in result._meta.fields
        assert "disconnect" in result._meta.fields
        assert "set" in result._meta.fields
        assert "create" in result._meta.fields
        assert "update" in result._meta.fields

    def test_generate_reverse_relation_input_type(self):
        """Should generate relation input type for reverse relations."""
        from rail_django.generators.types.relations import RelationInputTypeGenerator

        mock_type_gen = MagicMock()
        mock_type_gen.mutation_settings.relation_max_nesting_depth = 3
        mock_type_gen.generate_input_type.return_value = type(
            "MockInput", (graphene.InputObjectType,), {}
        )

        generator = RelationInputTypeGenerator(mock_type_gen)

        mock_model = MagicMock()
        mock_model._meta.label_lower = "test_app.post"
        mock_model._meta.model_name = "post"
        mock_model.__name__ = "Post"

        mock_parent = MagicMock()
        mock_parent._meta.model_name = "category"
        mock_parent.__name__ = "Category"

        result = generator.generate_relation_input_type(
            related_model=mock_model,
            relation_type="reverse",
            parent_model=mock_parent,
            depth=0,
            remote_field_name="category",
        )

        # Should return an InputObjectType class
        assert issubclass(result, graphene.InputObjectType)
        # Should have connect, disconnect, set for reverse
        assert "connect" in result._meta.fields
        assert "disconnect" in result._meta.fields
        assert "set" in result._meta.fields

    def test_caching_prevents_duplicate_types(self):
        """Generator should cache types and return same instance."""
        from rail_django.generators.types.relations import RelationInputTypeGenerator

        mock_type_gen = MagicMock()
        mock_type_gen.mutation_settings.relation_max_nesting_depth = 3
        mock_type_gen.generate_input_type.return_value = type(
            "MockInput", (graphene.InputObjectType,), {}
        )

        generator = RelationInputTypeGenerator(mock_type_gen)

        mock_model = MagicMock()
        mock_model._meta.label_lower = "test_app.author"
        mock_model._meta.model_name = "author"
        mock_model.__name__ = "Author"

        result1 = generator.generate_relation_input_type(
            related_model=mock_model,
            relation_type="fk",
            parent_model=None,
            depth=0,
        )

        result2 = generator.generate_relation_input_type(
            related_model=mock_model,
            relation_type="fk",
            parent_model=None,
            depth=0,
        )

        # Should return the same cached instance
        assert result1 is result2
        # Registry should have exactly one entry
        assert len(generator._registry) == 1

    def test_depth_limit_prevents_nested_create_update(self):
        """When depth >= max, should not include create/update fields."""
        from rail_django.generators.types.relations import RelationInputTypeGenerator

        mock_type_gen = MagicMock()
        mock_type_gen.mutation_settings.relation_max_nesting_depth = 2

        generator = RelationInputTypeGenerator(mock_type_gen)

        mock_model = MagicMock()
        mock_model._meta.label_lower = "test_app.author"
        mock_model._meta.model_name = "author"
        mock_model.__name__ = "Author"

        # Depth at limit
        result = generator.generate_relation_input_type(
            related_model=mock_model,
            relation_type="fk",
            parent_model=None,
            depth=2,  # At max depth
        )

        # Should still have connect (IDs don't need recursion)
        assert "connect" in result._meta.fields
        # Should NOT have create/update at depth limit
        assert "create" not in result._meta.fields
        assert "update" not in result._meta.fields

    def test_config_disables_operations(self):
        """FieldRelationConfig should control which operations are available."""
        from rail_django.generators.types.relations import RelationInputTypeGenerator
        from rail_django.generators.types.relation_config import (
            FieldRelationConfig,
            RelationOperationConfig,
        )

        mock_type_gen = MagicMock()
        mock_type_gen.mutation_settings.relation_max_nesting_depth = 3
        mock_type_gen.generate_input_type.return_value = type(
            "MockInput", (graphene.InputObjectType,), {}
        )

        generator = RelationInputTypeGenerator(mock_type_gen)

        mock_model = MagicMock()
        mock_model._meta.label_lower = "test_app.author"
        mock_model._meta.model_name = "author"
        mock_model.__name__ = "Author"

        # Config with create disabled
        config = FieldRelationConfig(
            connect=RelationOperationConfig(enabled=True),
            create=RelationOperationConfig(enabled=False),
            update=RelationOperationConfig(enabled=True),
        )

        result = generator.generate_relation_input_type(
            related_model=mock_model,
            relation_type="fk",
            parent_model=None,
            depth=0,
            config=config,
        )

        # Should have connect
        assert "connect" in result._meta.fields
        # Should NOT have create (disabled)
        assert "create" not in result._meta.fields
        # Should have update
        assert "update" in result._meta.fields


class TestRelationOperationConfig:
    """Tests for relation operation configuration dataclasses."""

    def test_default_config_enables_all(self):
        """Default FieldRelationConfig should enable all operations."""
        from rail_django.generators.types.relation_config import FieldRelationConfig

        config = FieldRelationConfig()

        assert config.connect.enabled is True
        assert config.create.enabled is True
        assert config.update.enabled is True
        assert config.disconnect.enabled is True
        assert config.set.enabled is True
        assert config.style == "unified"

    def test_operation_config_with_permission(self):
        """RelationOperationConfig should support permission requirements."""
        from rail_django.generators.types.relation_config import RelationOperationConfig

        config = RelationOperationConfig(
            enabled=True,
            require_permission="can_create_author",
        )

        assert config.enabled is True
        assert config.require_permission == "can_create_author"

    def test_config_custom_values(self):
        """FieldRelationConfig should accept custom operation configs."""
        from rail_django.generators.types.relation_config import (
            FieldRelationConfig,
            RelationOperationConfig,
        )

        config = FieldRelationConfig(
            style="id_only",
            connect=RelationOperationConfig(enabled=True),
            create=RelationOperationConfig(enabled=False),
            update=RelationOperationConfig(enabled=False),
            disconnect=RelationOperationConfig(enabled=True),
            set=RelationOperationConfig(enabled=False),
        )

        assert config.style == "id_only"
        assert config.connect.enabled is True
        assert config.create.enabled is False
        assert config.update.enabled is False
        assert config.disconnect.enabled is True
        assert config.set.enabled is False


class TestRelationOperationProcessor:
    """Tests for RelationOperationProcessor class."""

    def test_processor_initialization(self):
        """Processor should store handler reference."""
        from rail_django.generators.nested.operations import RelationOperationProcessor

        mock_handler = MagicMock()
        processor = RelationOperationProcessor(mock_handler)

        assert processor.handler is mock_handler

    def test_process_relation_operation_order(self):
        """Operations should be processed in correct order: set, disconnect, connect, create, update."""
        from rail_django.generators.nested.operations import RelationOperationProcessor

        mock_handler = MagicMock()
        processor = RelationOperationProcessor(mock_handler)

        mock_instance = MagicMock()
        call_order = []

        def track_connect(*args, **kwargs):
            call_order.append("connect")

        def track_create(*args, **kwargs):
            call_order.append("create")

        def track_disconnect(*args, **kwargs):
            call_order.append("disconnect")

        mock_handler.handle_connect = track_connect
        mock_handler.handle_create = track_create
        mock_handler.handle_disconnect = track_disconnect

        operations_data = {
            "create": [{"name": "New"}],  # Should be third
            "connect": ["1"],  # Should be second
            "disconnect": ["2"],  # Should be first
        }

        processor.process_relation(
            mock_instance,
            "tags",
            operations_data,
            info=None,
            is_m2m=True,
        )

        # Order should be: disconnect, connect, create
        assert call_order == ["disconnect", "connect", "create"]

    def test_process_relation_skips_none_values(self):
        """Processor should skip operations with None values."""
        from rail_django.generators.nested.operations import RelationOperationProcessor

        mock_handler = MagicMock()
        processor = RelationOperationProcessor(mock_handler)

        mock_instance = MagicMock()

        operations_data = {
            "connect": None,  # Should be skipped
            "create": [{"name": "New"}],  # Should be processed
        }

        processor.process_relation(
            mock_instance,
            "tags",
            operations_data,
            info=None,
            is_m2m=True,
        )

        # Connect should not be called (None value)
        mock_handler.handle_connect.assert_not_called()
        # Create should be called
        mock_handler.handle_create.assert_called_once()

    def test_dispatch_connect_operation(self):
        """Dispatch should call handler.handle_connect for connect operation."""
        from rail_django.generators.nested.operations import RelationOperationProcessor

        mock_handler = MagicMock()
        processor = RelationOperationProcessor(mock_handler)

        mock_instance = MagicMock()

        processor._dispatch(
            mock_instance,
            "author",
            "connect",
            "123",
            info=None,
            is_m2m=False,
            is_reverse=False,
        )

        mock_handler.handle_connect.assert_called_once_with(
            mock_instance, "author", "123", None, False, False
        )

    def test_dispatch_set_operation(self):
        """Dispatch should call handler.handle_set for set operation."""
        from rail_django.generators.nested.operations import RelationOperationProcessor

        mock_handler = MagicMock()
        processor = RelationOperationProcessor(mock_handler)

        mock_instance = MagicMock()

        processor._dispatch(
            mock_instance,
            "tags",
            "set",
            ["1", "2"],
            info=None,
            is_m2m=True,
            is_reverse=False,
        )

        mock_handler.handle_set.assert_called_once_with(
            mock_instance, "tags", ["1", "2"], None, True, False
        )


class TestRelationOperation:
    """Tests for RelationOperation dataclass."""

    def test_relation_operation_creation(self):
        """RelationOperation should store all required fields."""
        from rail_django.generators.nested.operations import RelationOperation

        mock_model = MagicMock()

        op = RelationOperation(
            operation="create",
            data={"name": "New Author"},
            field_name="author",
            related_model=mock_model,
        )

        assert op.operation == "create"
        assert op.data == {"name": "New Author"}
        assert op.field_name == "author"
        assert op.related_model is mock_model
