
import pytest
import graphene
from unittest.mock import Mock, patch
from django.db import models

from rail_django.generators.mutations.generator import MutationGenerator
from rail_django.core.settings.mutation_settings import MutationGeneratorSettings
from rail_django.generators.types.generator import TypeGenerator

class MockModel(models.Model):
    class Meta:
        app_label = "test_app"

class MockModelIncluded(models.Model):
    class Meta:
        app_label = "test_app"

class MockModelExcluded(models.Model):
    class Meta:
        app_label = "test_app"

class DummyMutation(graphene.Mutation):
    ok = graphene.Boolean()
    
    class Arguments:
        id = graphene.ID()

    @classmethod
    def mutate(cls, *args, **kwargs):
        return cls(ok=True)

@pytest.fixture
def type_generator():
    return Mock(spec=TypeGenerator)

@pytest.fixture
def mutation_generator(type_generator):
    gen = MutationGenerator(type_generator=type_generator)
    # Disable standard CRUD to focus on bulk and avoid mocking complexity for them
    gen.settings.enable_create = False
    gen.settings.enable_update = False
    gen.settings.enable_delete = False
    return gen

class TestBulkConfiguration:
    
    def test_bulk_disabled_globally(self, mutation_generator):
        """Test that nothing is generated if enable_bulk_operations is False."""
        mutation_generator.settings.enable_bulk_operations = False
        mutation_generator.settings.generate_bulk = True
        mutation_generator.settings.bulk_include_models = ["MockModel"]
        
        with patch.object(mutation_generator, 'generate_bulk_create_mutation') as mock_create:
            mutations = mutation_generator.generate_all_mutations(MockModel)
            assert "bulk_create_mock_model" not in mutations
            assert not mock_create.called

    def test_bulk_auto_discovery(self, mutation_generator):
        """Test that bulk mutations are generated for all models when generate_bulk is True."""
        mutation_generator.settings.enable_bulk_operations = True
        mutation_generator.settings.generate_bulk = True
        mutation_generator.settings.bulk_include_models = []
        mutation_generator.settings.bulk_exclude_models = []

        with patch.object(mutation_generator, 'generate_bulk_create_mutation') as mock_create, \
             patch.object(mutation_generator, 'generate_bulk_update_mutation') as mock_update, \
             patch.object(mutation_generator, 'generate_bulk_delete_mutation') as mock_delete:
            
            mock_create.return_value = DummyMutation
            mock_update.return_value = DummyMutation
            mock_delete.return_value = DummyMutation
            
            mutations = mutation_generator.generate_all_mutations(MockModel)
            assert "bulk_create_mock_model" in mutations
            assert mock_create.called

    def test_bulk_include_list(self, mutation_generator):
        """Test that only included models get bulk mutations when generate_bulk is False."""
        mutation_generator.settings.enable_bulk_operations = True
        mutation_generator.settings.generate_bulk = False
        mutation_generator.settings.bulk_include_models = ["MockModelIncluded"]
        mutation_generator.settings.bulk_exclude_models = []

        with patch.object(mutation_generator, 'generate_bulk_create_mutation') as mock_create, \
             patch.object(mutation_generator, 'generate_bulk_update_mutation') as mock_update, \
             patch.object(mutation_generator, 'generate_bulk_delete_mutation') as mock_delete:
            
            mock_create.return_value = DummyMutation
            mock_update.return_value = DummyMutation
            mock_delete.return_value = DummyMutation

            # Should be generated for Included
            mutations = mutation_generator.generate_all_mutations(MockModelIncluded)
            assert "bulk_create_mock_model_included" in mutations
            
            # Should NOT be generated for standard MockModel
            mutations_other = mutation_generator.generate_all_mutations(MockModel)
            assert "bulk_create_mock_model" not in mutations_other

    def test_bulk_exclude_list(self, mutation_generator):
        """Test that excluded models do NOT get bulk mutations even if generate_bulk is True."""
        mutation_generator.settings.enable_bulk_operations = True
        mutation_generator.settings.generate_bulk = True
        mutation_generator.settings.bulk_include_models = []
        mutation_generator.settings.bulk_exclude_models = ["MockModelExcluded"]

        with patch.object(mutation_generator, 'generate_bulk_create_mutation') as mock_create, \
             patch.object(mutation_generator, 'generate_bulk_update_mutation') as mock_update, \
             patch.object(mutation_generator, 'generate_bulk_delete_mutation') as mock_delete:
            
            mock_create.return_value = DummyMutation
            mock_update.return_value = DummyMutation
            mock_delete.return_value = DummyMutation

            # Should NOT be generated for Excluded
            mutations = mutation_generator.generate_all_mutations(MockModelExcluded)
            assert "bulk_create_mock_model_excluded" not in mutations
            
            # Should be generated for others
            mutations_other = mutation_generator.generate_all_mutations(MockModel)
            assert "bulk_create_mock_model" in mutations_other

    def test_bulk_include_overrides_generate_false(self, mutation_generator):
        """Test that include list works even if generate_bulk is False."""
        mutation_generator.settings.enable_bulk_operations = True
        mutation_generator.settings.generate_bulk = False
        mutation_generator.settings.bulk_include_models = ["MockModelIncluded"]

        with patch.object(mutation_generator, 'generate_bulk_create_mutation') as mock_create, \
             patch.object(mutation_generator, 'generate_bulk_update_mutation') as mock_update, \
             patch.object(mutation_generator, 'generate_bulk_delete_mutation') as mock_delete:
            
            mock_create.return_value = DummyMutation
            mock_update.return_value = DummyMutation
            mock_delete.return_value = DummyMutation

            mutations = mutation_generator.generate_all_mutations(MockModelIncluded)
            assert "bulk_create_mock_model_included" in mutations

    def test_exclude_wins_over_include(self, mutation_generator):
        """Test that exclusion takes precedence over inclusion."""
        mutation_generator.settings.enable_bulk_operations = True
        mutation_generator.settings.generate_bulk = False
        mutation_generator.settings.bulk_include_models = ["MockModel"]
        mutation_generator.settings.bulk_exclude_models = ["MockModel"]

        with patch.object(mutation_generator, 'generate_bulk_create_mutation') as mock_create:
             mutations = mutation_generator.generate_all_mutations(MockModel)
             assert "bulk_create_mock_model" not in mutations

