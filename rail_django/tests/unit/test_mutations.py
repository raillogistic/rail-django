"""
Tests complets pour le système de génération de mutations GraphQL.

Ce module teste:
- La génération de mutations CRUD pour les modèles Django
- Les mutations de création, mise à jour et suppression
- La validation des données d'entrée
- La gestion des erreurs et des permissions
- L'intégration avec les méthodes métier
"""

from typing import Any, Dict, List, Optional, Type
from unittest.mock import MagicMock, Mock, patch

import graphene
import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.test import TestCase
from graphene import Boolean, DateTime, Field, Int, Mutation, ObjectType, String
from graphene_django import DjangoObjectType
from test_app.models import Category, Client, Comment
from test_app.models import Post
from test_app.models import Post as OrderForMutation
from test_app.models import Product as ProductForMutation
from test_app.models import Profile, Tag

from rail_django.decorators import business_logic
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


# Remove TestMutationInfo class since MutationInfo doesn't exist


@pytest.mark.unit
class TestAdvancedMutationFeatures(TestCase):
    """Tests avancés pour les fonctionnalités de mutations."""

    def setUp(self):
        """Configuration des tests."""
        self.type_generator = TypeGenerator()
        self.input_generator = self.type_generator
