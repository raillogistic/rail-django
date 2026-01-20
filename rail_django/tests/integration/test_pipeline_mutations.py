"""
Integration tests for the mutation pipeline architecture.

These tests verify that the pipeline-based mutations work correctly
with real Django models and database operations.
"""

import pytest
from django.test import TestCase, override_settings
from unittest.mock import Mock, patch

from test_app.models import Category, Product, Tag


def grant_model_permissions(user, model, permissions):
    """Grant permissions for a model to a user."""
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(model)
    for perm_codename in permissions:
        permission = Permission.objects.get(
            codename=perm_codename, content_type=content_type
        )
        user.user_permissions.add(permission)


def create_mock_graphql_info(user):
    """Create a properly mocked GraphQL info object for testing mutations."""
    from django.http import HttpRequest

    # Use spec to prevent Mock from auto-generating attributes
    mock_request = Mock(spec=HttpRequest)
    mock_request.META = {}
    mock_request.user = user
    mock_request.path = "/graphql/"
    mock_request.method = "POST"
    mock_request.session = Mock()
    mock_request.session.session_key = None

    mock_info = Mock()
    mock_info.context = mock_request
    return mock_info


@pytest.mark.integration
class TestPipelineMutationGenerator(TestCase):
    """Integration tests for pipeline-based mutation generation."""

    def setUp(self):
        """Set up test fixtures."""
        from rail_django.generators.types import TypeGenerator
        from rail_django.generators.mutations import MutationGenerator
        from rail_django.core.settings import MutationGeneratorSettings

        self.type_generator = TypeGenerator()

        # Create settings for the mutation generator
        self.settings = MutationGeneratorSettings(
            enable_create=True,
            enable_update=True,
            enable_delete=True,
        )

        self.mutation_generator = MutationGenerator(
            self.type_generator,
            settings=self.settings,
        )

    def test_generate_create_mutation_with_pipeline(self):
        """Test that create mutation is generated using pipeline backend."""
        mutation = self.mutation_generator.generate_create_mutation(Category)

        self.assertIsNotNone(mutation)
        self.assertTrue(hasattr(mutation, "Arguments"))
        self.assertTrue(hasattr(mutation, "mutate"))
        self.assertTrue(hasattr(mutation, "pipeline"))

    def test_generate_update_mutation_with_pipeline(self):
        """Test that update mutation is generated using pipeline backend."""
        mutation = self.mutation_generator.generate_update_mutation(Category)

        self.assertIsNotNone(mutation)
        self.assertTrue(hasattr(mutation, "Arguments"))
        self.assertTrue(hasattr(mutation, "mutate"))
        self.assertTrue(hasattr(mutation, "pipeline"))

    def test_generate_delete_mutation_with_pipeline(self):
        """Test that delete mutation is generated using pipeline backend."""
        mutation = self.mutation_generator.generate_delete_mutation(Category)

        self.assertIsNotNone(mutation)
        self.assertTrue(hasattr(mutation, "Arguments"))
        self.assertTrue(hasattr(mutation, "mutate"))
        self.assertTrue(hasattr(mutation, "pipeline"))

    def test_pipeline_mutation_has_correct_steps(self):
        """Test that pipeline mutation has expected steps."""
        mutation = self.mutation_generator.generate_create_mutation(Category)

        step_names = mutation.pipeline.get_step_names()

        # Verify core steps are present
        self.assertIn("authentication", step_names)
        self.assertIn("sanitization", step_names)
        self.assertIn("create_execution", step_names)


@pytest.mark.integration
class TestPipelineCreateMutation(TestCase):
    """Integration tests for create mutations using pipeline."""

    def setUp(self):
        """Set up test fixtures."""
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        grant_model_permissions(self.user, Category, ["add_category"])

    def test_create_mutation_executes_successfully(self):
        """Test that create mutation works end-to-end."""
        from rail_django.generators.types import TypeGenerator
        from rail_django.generators.mutations import MutationGenerator
        from rail_django.core.settings import MutationGeneratorSettings

        settings = MutationGeneratorSettings()
        type_generator = TypeGenerator()
        mutation_generator = MutationGenerator(type_generator, settings=settings)

        mutation = mutation_generator.generate_create_mutation(Category)

        mock_info = create_mock_graphql_info(self.user)

        # Execute mutation
        result = mutation.mutate(
            None,
            mock_info,
            input={"name": "Test Category"},
        )

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.object)
        self.assertEqual(result.object.name, "Test Category")

    def test_create_mutation_validates_input(self):
        """Test that create mutation validates input correctly."""
        from rail_django.generators.types import TypeGenerator
        from rail_django.generators.mutations import MutationGenerator
        from rail_django.core.settings import MutationGeneratorSettings

        settings = MutationGeneratorSettings()
        type_generator = TypeGenerator()
        mutation_generator = MutationGenerator(type_generator, settings=settings)

        mutation = mutation_generator.generate_create_mutation(Category)

        # Create mock GraphQL info with unauthenticated user
        mock_user = Mock()
        mock_user.is_authenticated = False

        mock_info = create_mock_graphql_info(mock_user)

        # Execute mutation - should fail due to authentication
        result = mutation.mutate(
            None,
            mock_info,
            input={"name": "Test Category"},
        )

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.errors)


@pytest.mark.integration
class TestPipelineUpdateMutation(TestCase):
    """Integration tests for update mutations using pipeline."""

    def setUp(self):
        """Set up test fixtures."""
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        grant_model_permissions(self.user, Category, ["change_category"])
        self.category = Category.objects.create(name="Original Category")

    def test_update_mutation_executes_successfully(self):
        """Test that update mutation works end-to-end."""
        from rail_django.generators.types import TypeGenerator
        from rail_django.generators.mutations import MutationGenerator
        from rail_django.core.settings import MutationGeneratorSettings

        settings = MutationGeneratorSettings()
        type_generator = TypeGenerator()
        mutation_generator = MutationGenerator(type_generator, settings=settings)

        mutation = mutation_generator.generate_update_mutation(Category)

        mock_info = create_mock_graphql_info(self.user)

        # Execute mutation
        result = mutation.mutate(
            None,
            mock_info,
            id=str(self.category.pk),
            input={"name": "Updated Category"},
        )

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.object)
        self.assertEqual(result.object.name, "Updated Category")

    def test_update_mutation_handles_missing_instance(self):
        """Test that update mutation handles missing instance correctly."""
        from rail_django.generators.types import TypeGenerator
        from rail_django.generators.mutations import MutationGenerator
        from rail_django.core.settings import MutationGeneratorSettings

        settings = MutationGeneratorSettings()
        type_generator = TypeGenerator()
        mutation_generator = MutationGenerator(type_generator, settings=settings)

        mutation = mutation_generator.generate_update_mutation(Category)

        mock_info = create_mock_graphql_info(self.user)

        # Execute mutation with non-existent ID
        result = mutation.mutate(
            None,
            mock_info,
            id="99999",
            input={"name": "Updated Category"},
        )

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.errors)


@pytest.mark.integration
class TestPipelineDeleteMutation(TestCase):
    """Integration tests for delete mutations using pipeline."""

    def setUp(self):
        """Set up test fixtures."""
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        grant_model_permissions(self.user, Category, ["delete_category"])
        self.category = Category.objects.create(name="Category to Delete")

    def test_delete_mutation_executes_successfully(self):
        """Test that delete mutation works end-to-end."""
        from rail_django.generators.types import TypeGenerator
        from rail_django.generators.mutations import MutationGenerator
        from rail_django.core.settings import MutationGeneratorSettings

        settings = MutationGeneratorSettings()
        type_generator = TypeGenerator()
        mutation_generator = MutationGenerator(type_generator, settings=settings)

        mutation = mutation_generator.generate_delete_mutation(Category)

        mock_info = create_mock_graphql_info(self.user)

        category_id = self.category.pk

        # Execute mutation
        result = mutation.mutate(
            None,
            mock_info,
            id=str(category_id),
        )

        self.assertTrue(result.ok)
        self.assertFalse(Category.objects.filter(pk=category_id).exists())


@pytest.mark.integration
class TestGraphQLMetaPipelineConfig(TestCase):
    """Integration tests for GraphQLMeta pipeline configuration."""

    def test_pipeline_config_is_loaded(self):
        """Test that pipeline configuration is loaded from GraphQLMeta."""
        from rail_django.core.meta import get_model_graphql_meta, PipelineConfig

        # Test with a model that has GraphQLMeta
        meta = get_model_graphql_meta(Category)

        self.assertIsNotNone(meta)
        self.assertIsNotNone(meta.pipeline_config)
        self.assertIsInstance(meta.pipeline_config, PipelineConfig)

    def test_pipeline_config_defaults(self):
        """Test that pipeline configuration has correct defaults."""
        from rail_django.core.meta import PipelineConfig

        config = PipelineConfig()

        self.assertEqual(config.extra_steps, [])
        self.assertEqual(config.skip_steps, [])
        self.assertEqual(config.step_order, {})
        self.assertEqual(config.create_steps, [])
        self.assertEqual(config.update_steps, [])
        self.assertEqual(config.delete_steps, [])
