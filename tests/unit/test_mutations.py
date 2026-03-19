"""
Tests complets pour le système de génération de mutations GraphQL.

Ce module teste:
- La génération de mutations CRUD pour les modèles Django
- Les mutations de création, mise à jour et suppression
- La validation des données d'entrée
- La gestion des erreurs et des permissions
- L'intégration avec les méthodes métier
"""

from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Type
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import graphene
import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.test import TestCase
from graphene import Boolean, DateTime, Field, Int, Mutation, ObjectType, String
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from test_app.models import Category, Client, Comment
from test_app.models import Post
from test_app.models import Post as OrderForMutation
from test_app.models import Product as ProductForMutation
from test_app.models import Profile, Tag

from rail_django.core.decorators import business_logic, mutation
from rail_django.core.settings import MutationGeneratorSettings
from rail_django.generators.introspector import ModelIntrospector
from rail_django.generators.mutations import MutationError, MutationGenerator
from rail_django.generators.types import TypeGenerator

# Test classes start here


class TestMutationGenerator(TestCase):
    """Tests pour la classe MutationGenerator."""

    def setUp(self):
        """Configuration des tests."""
        self.introspector = ModelIntrospector(Category)
        self.type_generator = TypeGenerator()
        self.input_generator = self.type_generator
        self.mutation_generator = MutationGenerator(self.type_generator)

    def test_initialization(self):
        """Test l'initialisation du générateur de mutations."""
        # Test initialisation de base
        generator = MutationGenerator(self.type_generator)
        self.assertIsNotNone(generator)
        self.assertEqual(generator.type_generator, self.type_generator)

        # Test initialisation avec configuration
        from rail_django.core.settings import MutationGeneratorSettings

        settings_mock = MutationGeneratorSettings()
        generator_with_config = MutationGenerator(
            self.type_generator, settings=settings_mock
        )
        self.assertEqual(generator_with_config.settings, settings_mock)

    def test_generate_create_mutation(self):
        """Test la génération de mutation de création."""
        # Générer la mutation de création pour Category
        create_mutation = self.mutation_generator.generate_create_mutation(Category)

        # Vérifier que la mutation est générée
        self.assertIsNotNone(create_mutation)
        self.assertTrue(issubclass(create_mutation, Mutation))

        # Vérifier que la mutation a les champs requis
        self.assertTrue(hasattr(create_mutation, "Arguments"))
        self.assertTrue(hasattr(create_mutation, "mutate"))

    def test_generate_update_mutation(self):
        """Test la génération de mutation de mise à jour."""
        # Générer la mutation de mise à jour pour Category
        update_mutation = self.mutation_generator.generate_update_mutation(Category)

        # Vérifier que la mutation est générée
        self.assertIsNotNone(update_mutation)
        self.assertTrue(issubclass(update_mutation, Mutation))

        # Vérifier que la mutation a un argument ID
        if hasattr(update_mutation, "Arguments"):
            args = update_mutation.Arguments
            self.assertTrue(hasattr(args, "id"))

    def test_generate_delete_mutation(self):
        """Test la génération de mutation de suppression."""
        # Générer la mutation de suppression pour Category
        delete_mutation = self.mutation_generator.generate_delete_mutation(Category)

        # Vérifier que la mutation est générée
        self.assertIsNotNone(delete_mutation)
        self.assertTrue(issubclass(delete_mutation, Mutation))

        # Vérifier que la mutation a un argument ID
        if hasattr(delete_mutation, "Arguments"):
            args = delete_mutation.Arguments
            self.assertTrue(hasattr(args, "id"))

    def test_input_type_generation(self):
        """Test la génération des types d'entrée."""
        # Générer le type d'entrée pour TestProduct
        input_type = self.input_generator.generate_input_type(ProductForMutation, "create")

        # Vérifier que le type d'entrée est généré
        self.assertIsNotNone(input_type)

        # Vérifier que le type d'entrée a les champs appropriés
        if hasattr(input_type, "_meta"):
            fields = input_type._meta.fields
            self.assertIn("name", fields)  # Changed from nom_produit to name
            self.assertIn("price", fields)  # Changed from prix_produit to price

    def test_mutation_validation(self):
        """Test la validation des données dans les mutations."""
        # Créer une mutation avec validation
        create_mutation = self.mutation_generator.generate_create_mutation(ProductForMutation)

        # Vérifier que la mutation peut être instanciée
        self.assertIsNotNone(create_mutation)

        # La validation sera testée lors de l'exécution
        self.assertTrue(hasattr(create_mutation, "mutate"))

    def test_mutation_with_relationships(self):
        """Test la génération de mutations avec relations."""
        # Générer la mutation pour OrderForMutation (qui a des relations)
        order_mutation = self.mutation_generator.generate_create_mutation(OrderForMutation)

        # Vérifier que la mutation est générée
        self.assertIsNotNone(order_mutation)
        self.assertTrue(issubclass(order_mutation, Mutation))

        # La mutation doit pouvoir gérer les relations
        self.assertTrue(hasattr(order_mutation, "mutate"))

    def test_mutation_error_handling(self):
        """Test la gestion d'erreurs dans les mutations."""
        # Générer une mutation avec gestion d'erreurs
        create_mutation = self.mutation_generator.generate_create_mutation(ProductForMutation)

        # Vérifier que la mutation est générée
        self.assertIsNotNone(create_mutation)

        # La mutation doit avoir une méthode mutate qui gère les erreurs
        self.assertTrue(hasattr(create_mutation, "mutate"))

    def test_error_handling_invalid_model(self):
        """Test la gestion d'erreurs pour un modèle invalide."""
        with self.assertRaises((AttributeError, TypeError, ValueError)):
            self.mutation_generator.generate_create_mutation(None)

    def test_performance_large_model(self):
        """Test les performances avec un modèle complexe."""
        import time

        # Mesurer le temps de génération
        start_time = time.time()
        all_mutations = self.mutation_generator.generate_all_mutations(OrderForMutation)
        end_time = time.time()

        # La génération doit être rapide (moins de 500ms)
        execution_time = end_time - start_time
        self.assertLess(execution_time, 0.5)

        # Vérifier que les mutations sont générées
        self.assertIsNotNone(all_mutations)

    def test_logging_functionality(self):
        """Test que les fonctionnalités de logging fonctionnent correctement."""
        self.skipTest("Mutations module structure has changed")

    def test_method_mutation_temporal_annotations_map_to_graphql_temporal_scalars(self):
        """Temporal method annotations should produce temporal GraphQL input scalars."""
        original_method = getattr(Category, "schedule_window", None)

        @mutation(description="Schedule category window")
        def schedule_window(
            self,
            starts_on: date,
            starts_at: datetime,
            reminder_at: time | None = None,
        ) -> bool:
            return True

        try:
            Category.schedule_window = schedule_window
            mutation_class = self.mutation_generator.generate_method_mutation(
                Category,
                ModelIntrospector.for_model(Category).get_model_methods()[
                    "schedule_window"
                ],
            )

            self.assertIsNotNone(mutation_class)
            input_type = mutation_class.Arguments.input._type.of_type
            fields = input_type._meta.fields

            self.assertEqual(fields["starts_on"].type.__name__, "Date")
            self.assertEqual(fields["starts_at"].type.__name__, "DateTime")
            self.assertEqual(fields["reminder_at"].type.__name__, "Time")
        finally:
            if original_method is None and hasattr(Category, "schedule_window"):
                delattr(Category, "schedule_window")
            elif original_method is not None:
                Category.schedule_window = original_method


class TestInputTypeGenerator(TestCase):
    """Tests pour la classe InputTypeGenerator."""

    def setUp(self):
        """Configuration des tests."""
        self.introspector = ModelIntrospector(ProductForMutation)
        self.type_generator = TypeGenerator()
        self.input_generator = self.type_generator

    def test_generate_create_input_type(self):
        """Test la génération de type d'entrée pour création."""
        # Générer le type d'entrée pour ProductForMutation
        create_input = self.input_generator.generate_input_type(ProductForMutation, "create")

        # Vérifier que le type d'entrée est généré
        self.assertIsNotNone(create_input)

        # Vérifier que les champs appropriés sont présents
        if hasattr(create_input, "_meta"):
            fields = create_input._meta.fields
            self.assertIn("name", fields)  # Changed from nom_produit to name
            self.assertIn("price", fields)  # Changed from prix_produit to price
            # Les champs auto ne doivent pas être présents
            self.assertNotIn("date_creation", fields)

    def test_generate_update_input_type(self):
        """Test la génération de type d'entrée pour mise à jour."""
        # Générer le type d'entrée pour mise à jour
        update_input = self.input_generator.generate_input_type(ProductForMutation, "update")

        # Vérifier que le type d'entrée est généré
        self.assertIsNotNone(update_input)

        # Vérifier que les champs sont optionnels pour la mise à jour
        if hasattr(update_input, "_meta"):
            fields = update_input._meta.fields
            # Tous les champs modifiables doivent être présents mais optionnels
            self.assertIn("name", fields)  # Changed from nom_produit to name
            self.assertIn("price", fields)  # Changed from prix_produit to price

    def test_input_type_field_validation(self):
        """Test la validation des champs dans les types d'entrée."""
        # Générer le type d'entrée
        input_type = self.input_generator.generate_input_type(ProductForMutation, "create")

        # Vérifier que le type d'entrée est généré
        self.assertIsNotNone(input_type)

        # Les validations seront testées lors de l'utilisation
        if hasattr(input_type, "_meta"):
            self.assertIsNotNone(input_type._meta.fields)

    def test_input_type_with_relationships(self):
        """Test la génération de types d'entrée avec relations."""
        # Générer le type d'entrée pour Post (qui a des relations)
        post_input = self.input_generator.generate_input_type(Post, "create")

        # Vérifier que le type d'entrée est généré
        self.assertIsNotNone(post_input)

        # Vérifier que les relations sont gérées
        if hasattr(post_input, "_meta"):
            fields = post_input._meta.fields
            # Les clés étrangères doivent être présentes
            self.assertIn("category", fields)


    def test_input_type_respects_mandatory_field_metadata(self):
        """Mandatory metadata should mark optional fields as required."""
        type_generator = TypeGenerator()

        with patch.object(
            type_generator,
            "_get_model_meta",
            return_value=SimpleNamespace(
                mandatory_fields=["description"],
                exclude_fields=[],
                include_fields=None,
                should_expose_field=lambda *_args, **_kwargs: True,
            ),
        ):
            create_input = type_generator.generate_input_type(Category, "create")

        description_field = create_input._meta.fields["description"]
        self.assertTrue(hasattr(description_field._type, "_of_type"))


# Remove TestMutationInfo class since MutationInfo doesn't exist


@pytest.mark.unit
class TestAdvancedMutationFeatures(TestCase):
    """Tests avancés pour les fonctionnalités de mutations."""

    def setUp(self):
        """Configuration des tests."""
        self.type_generator = TypeGenerator()
        self.input_generator = self.type_generator


class UnmanagedTestModel(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "test_app"
        managed = False


class TestUnmanagedMutations(TestCase):
    def setUp(self):
        self.type_generator = TypeGenerator()
        self.mutation_generator = MutationGenerator(self.type_generator)

    def test_no_mutations_for_unmanaged_model(self):
        mutations = self.mutation_generator.generate_all_mutations(UnmanagedTestModel)
        self.assertNotIn("createUnmanagedTestModel", mutations)
        self.assertNotIn("updateUnmanagedTestModel", mutations)
        self.assertNotIn("deleteUnmanagedTestModel", mutations)
        self.assertNotIn("bulkCreateUnmanagedTestModel", mutations)
        self.assertNotIn("bulkUpdateUnmanagedTestModel", mutations)
        self.assertNotIn("bulkDeleteUnmanagedTestModel", mutations)


@pytest.mark.unit
def test_mutation_generator_tenant_scope_runtime_error_fails_closed():
    generator = MutationGenerator(TypeGenerator())
    queryset = Mock()
    info = Mock()

    with patch(
        "rail_django.extensions.multitenancy.apply_tenant_queryset",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(GraphQLError, match="Tenant scope enforcement failed"):
            generator._apply_tenant_scope(queryset, info, Category)


@pytest.mark.unit
def test_mutation_generator_tenant_scope_runtime_error_can_fail_open():
    generator = MutationGenerator(
        TypeGenerator(),
        settings=MutationGeneratorSettings(fail_open_on_multitenancy_errors=True),
    )
    queryset = Mock()
    info = Mock()

    with patch(
        "rail_django.extensions.multitenancy.apply_tenant_queryset",
        side_effect=RuntimeError("boom"),
    ):
        result = generator._apply_tenant_scope(queryset, info, Category)

    assert result is queryset


@pytest.mark.django_db
class TestCustomMethodMutationContracts:
    def setup_method(self):
        self.generator = MutationGenerator(TypeGenerator())
        self.category = Category.objects.create(name="alpha", description="")
        self.user = User.objects.create_user(
            username="custom_method_user",
            password="pass12345",
        )
        self.info = Mock()
        self.info.context = Mock()
        self.info.context.user = self.user

    def teardown_method(self):
        ModelIntrospector.clear_cache()
        if hasattr(Category, "_graphql_meta_instance"):
            delattr(Category, "_graphql_meta_instance")

    def test_generate_method_mutation_supports_custom_input_and_output_types(self):
        class ActivateInput(graphene.InputObjectType):
            note = graphene.String(required=True)

        class ActivatePayload(graphene.ObjectType):
            message = graphene.String()

        @mutation(input_type=ActivateInput, output_type=ActivatePayload)
        def activate(self, note: str):
            self.description = note
            self.save(update_fields=["description"])
            return {"message": note}

        original_method = getattr(Category, "activate", None)
        Category.activate = activate

        try:
            method_info = ModelIntrospector(Category).get_model_methods()["activate"]
            mutation_class = self.generator.generate_method_mutation(
                Category,
                method_info,
            )

            assert "result" in mutation_class._meta.fields
            assert mutation_class._meta.fields["result"].type == ActivatePayload

            runtime_input = SimpleNamespace(
                note="hello",
                _meta=SimpleNamespace(fields={"note": object()}),
            )

            result = mutation_class.mutate(
                None,
                self.info,
                id=str(self.category.id),
                input=runtime_input,
            )

            self.category.refresh_from_db()
            assert result.ok is True
            assert self.category.description == "hello"
        finally:
            if original_method is None:
                delattr(Category, "activate")
            else:
                Category.activate = original_method
            ModelIntrospector.clear_cache()

    def test_convert_method_to_mutation_supports_custom_input_type(self):
        class RenameInput(graphene.InputObjectType):
            note = graphene.String(required=True)

        def rename(self, note: str):
            self.description = note
            self.save(update_fields=["description"])
            return True

        original_method = getattr(Category, "rename", None)
        Category.rename = rename

        try:
            mutation_class = self.generator.convert_method_to_mutation(
                Category,
                "rename",
                custom_input_type=RenameInput,
            )

            assert hasattr(mutation_class.Arguments, "input")

            result = mutation_class.mutate(
                None,
                self.info,
                id=str(self.category.id),
                input={"note": "renamed"},
            )

            self.category.refresh_from_db()
            assert result.ok is True
            assert self.category.description == "renamed"
        finally:
            if original_method is None:
                delattr(Category, "rename")
            else:
                Category.rename = original_method
            ModelIntrospector.clear_cache()

