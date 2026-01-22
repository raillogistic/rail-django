"""
Tests unitaires pour les décorateurs de rail_django.

Ce module contient des tests complets pour les décorateurs,
en particulier le décorateur @register_schema pour l'enregistrement de schémas.
"""

import logging
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

from django.apps import apps
from django.test import TestCase

from rail_django.decorators import (
    business_logic,
    custom_mutation_name,
    mutation,
    private_method,
    register_schema,
)


class TestRegisterSchemaDecorator(TestCase):
    """Tests pour le décorateur @register_schema."""

    def setUp(self):
        """Configuration initiale pour chaque test."""
        # Mock du registre de schémas
        self.mock_registry = Mock()
        self.mock_registry.register_schema.return_value = Mock()

        # Patch du registre global
        self.registry_patcher = patch(
            "rail_django.core.registry.schema_registry", self.mock_registry
        )
        self.registry_patcher.start()

    def tearDown(self):
        """Nettoyage après chaque test."""
        self.registry_patcher.stop()

    def test_register_schema_class_decorator(self):
        """Test du décorateur @register_schema sur une classe."""

        @register_schema(
            name="test_class_schema",
            description="Test schema from class",
            version="1.0.0",
        )
        class TestSchema:
            """Classe de test pour le schéma."""

            pass

        # Vérifier que le registre a été appelé
        self.mock_registry.register_schema.assert_called_once()
        call_args = self.mock_registry.register_schema.call_args

        # Vérifier les arguments passés
        self.assertEqual(call_args[1]["name"], "test_class_schema")
        self.assertEqual(call_args[1]["description"], "Test schema from class")

        # Vérifier que la classe est retournée inchangée
        self.assertEqual(TestSchema.__name__, "TestSchema")

    def test_register_schema_function_decorator(self):
        """Test du décorateur @register_schema sur une fonction."""

        @register_schema(
            name="test_function_schema", description="Test schema from function"
        )
        def test_schema_function():
            """Fonction de test pour le schéma."""
            return "test_schema"

        # Vérifier que le registre a été appelé
        self.mock_registry.register_schema.assert_called_once()
        call_args = self.mock_registry.register_schema.call_args

        # Vérifier les arguments passés
        self.assertEqual(call_args[1]["name"], "test_function_schema")
        self.assertEqual(call_args[1]["description"], "Test schema from function")

        # Vérifier que la fonction est retournée inchangée
        self.assertEqual(test_schema_function(), "test_schema")

    def test_register_schema_with_all_parameters(self):
        """Test du décorateur avec tous les paramètres possibles."""

        @register_schema(
            name="full_param_schema",
            description="Schema with all parameters",
            apps=["app1", "app2"],
            models=["Model1", "Model2"],
            settings={"custom_setting": "value"},
            enabled=True,
        )
        class FullParamSchema:
            pass

        # Vérifier tous les paramètres
        call_args = self.mock_registry.register_schema.call_args[1]

        self.assertEqual(call_args["name"], "full_param_schema")
        self.assertEqual(call_args["description"], "Schema with all parameters")
        self.assertEqual(call_args["apps"], ["app1", "app2"])
        self.assertEqual(call_args["models"], ["Model1", "Model2"])
        self.assertEqual(call_args["settings"], {"custom_setting": "value"})
        self.assertEqual(call_args["enabled"], True)

    def test_register_schema_minimal_parameters(self):
        """Test du décorateur avec seulement le nom (paramètre minimal)."""

        @register_schema(name="minimal_schema")
        class MinimalSchema:
            pass

        # Vérifier que seuls les paramètres par défaut sont utilisés
        call_args = self.mock_registry.register_schema.call_args[1]

        self.assertEqual(call_args["name"], "minimal_schema")
        self.assertEqual(call_args.get("description", ""), "")
        self.assertTrue(call_args.get("enabled", True))

    def test_register_schema_error_handling(self):
        """Test la gestion d'erreurs du décorateur."""

        # Simuler une erreur lors de l'enregistrement
        self.mock_registry.register_schema.side_effect = ValueError(
            "Registration failed"
        )

        with patch("rail_django.decorators.logger") as mock_logger:

            @register_schema(name="error_schema")
            class ErrorSchema:
                pass

            # Vérifier que l'erreur a été loggée
            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args[0][0]
            self.assertIn("Failed to register schema", error_call)
            self.assertIn("error_schema", error_call)

    def test_register_schema_without_name_raises_error(self):
        """Test qu'un schéma sans nom utilise le nom de la classe."""

        @register_schema()  # Pas de nom fourni
        class NoNameSchema:
            pass

        # Vérifier que le schéma a été enregistré avec le nom de la classe
        call_args = self.mock_registry.register_schema.call_args[1]
        self.assertEqual(call_args["name"], "NoNameSchema")

    def test_register_schema_with_invalid_name_type(self):
        """Test avec un nom de schéma de type invalide."""

        @register_schema(name=123)  # Nom non-string
        class InvalidNameSchema:
            pass

        # Le décorateur devrait conserver le nom tel quel
        call_args = self.mock_registry.register_schema.call_args[1]
        self.assertEqual(call_args["name"], 123)

    def test_register_schema_preserves_class_attributes(self):
        """Test que le décorateur préserve les attributs de classe."""

        @register_schema(name="preserve_attrs_schema")
        class PreserveAttrsSchema:
            """Docstring de test."""

            class_attr = "test_value"

            def method(self):
                return "test_method"

        # Vérifier que les attributs sont préservés
        self.assertEqual(PreserveAttrsSchema.__doc__, "Docstring de test.")
        self.assertEqual(PreserveAttrsSchema.class_attr, "test_value")
        self.assertTrue(hasattr(PreserveAttrsSchema, "method"))

        # Vérifier que la méthode fonctionne
        instance = PreserveAttrsSchema()
        self.assertEqual(instance.method(), "test_method")

    def test_register_schema_multiple_decorators(self):
        """Test de l'utilisation de plusieurs décorateurs @register_schema."""

        @register_schema(name="schema1")
        class Schema1:
            pass

        @register_schema(name="schema2")
        class Schema2:
            pass

        # Vérifier que les deux schémas ont été enregistrés
        self.assertEqual(self.mock_registry.register_schema.call_count, 2)

        # Vérifier les noms des schémas
        calls = self.mock_registry.register_schema.call_args_list
        schema_names = [call[1]["name"] for call in calls]
        self.assertIn("schema1", schema_names)
        self.assertIn("schema2", schema_names)


class TestExistingDecorators(TestCase):
    """Tests pour les décorateurs existants (régression)."""

    def test_mutation_decorator(self):
        """Test que le décorateur @mutation fonctionne toujours."""

        @mutation()
        def test_mutation_method(self):
            """Méthode de test pour mutation."""
            return "mutation_result"

        # Vérifier que la fonction a l'attribut _is_mutation
        self.assertTrue(hasattr(test_mutation_method, "_is_mutation"))
        self.assertTrue(test_mutation_method._is_mutation)

    def test_business_logic_decorator(self):
        """Test que le décorateur @business_logic fonctionne toujours."""

        @business_logic()
        def test_business_method(self):
            """Méthode de test pour business logic."""
            return "business_result"

        # Vérifier que la fonction a l'attribut _is_business_logic
        self.assertTrue(hasattr(test_business_method, "_is_business_logic"))
        self.assertTrue(test_business_method._is_business_logic)

    def test_private_method_decorator(self):
        """Test que le décorateur @private_method fonctionne toujours."""

        @private_method
        def test_private_method(self):
            """Méthode de test pour private method."""
            return "private_result"

        # Vérifier que la fonction a l'attribut _private
        self.assertTrue(hasattr(test_private_method, "_private"))
        self.assertTrue(test_private_method._private)

    def test_custom_mutation_name_decorator(self):
        """Test que le décorateur @custom_mutation_name fonctionne toujours."""

        @custom_mutation_name("customMutationName")
        def test_custom_name_method(self):
            """Méthode de test pour custom mutation name."""
            return "custom_name_result"

        # Vérifier que la fonction a l'attribut _custom_mutation_name
        self.assertTrue(hasattr(test_custom_name_method, "_custom_mutation_name"))
        self.assertEqual(
            test_custom_name_method._custom_mutation_name, "customMutationName"
        )


class TestDecoratorIntegration(TestCase):
    """Tests d'intégration pour les décorateurs."""

    def setUp(self):
        """Configuration pour les tests d'intégration."""
        self.mock_registry = Mock()
        self.registry_patcher = patch(
            "rail_django.core.registry.schema_registry", self.mock_registry
        )
        self.registry_patcher.start()

    def tearDown(self):
        """Nettoyage après les tests d'intégration."""
        self.registry_patcher.stop()

    def test_combined_decorators(self):
        """Test de l'utilisation combinée de décorateurs."""

        @register_schema(name="combined_schema")
        class CombinedSchema:
            @mutation()
            def create_item(self):
                return "created"

            @business_logic()
            def process_item(self):
                return "processed"

            @private_method
            def internal_method(self):
                return "internal"

        # Vérifier que le schéma a été enregistré
        self.mock_registry.register_schema.assert_called_once()

        # Vérifier que les méthodes ont leurs attributs
        self.assertTrue(CombinedSchema.create_item._is_mutation)
        self.assertTrue(CombinedSchema.process_item._is_business_logic)
        self.assertTrue(CombinedSchema.internal_method._private)

    def test_decorator_order_independence(self):
        """Test que l'ordre des décorateurs n'affecte pas le résultat."""

        @register_schema(name="order_test_schema")
        @mutation()
        def decorated_function():
            return "result"

        # Vérifier que les deux décorateurs ont été appliqués
        self.mock_registry.register_schema.assert_called_once()
        self.assertTrue(decorated_function._is_mutation)


class TestDecoratorLogging(TestCase):
    """Tests pour le logging des décorateurs."""

    def setUp(self):
        """Configuration pour les tests de logging."""
        self.mock_registry = Mock()
        self.registry_patcher = patch(
            "rail_django.core.registry.schema_registry", self.mock_registry
        )
        self.registry_patcher.start()

    def tearDown(self):
        """Nettoyage après les tests de logging."""
        self.registry_patcher.stop()

    @patch("rail_django.decorators.logger")
    def test_successful_registration_logging(self, mock_logger):
        """Test du logging lors d'un enregistrement réussi."""

        @register_schema(name="logging_test_schema")
        class LoggingTestSchema:
            pass

        # Vérifier que le succès a été loggé
        mock_logger.info.assert_called_once()
        info_call = mock_logger.info.call_args[0][0]
        self.assertIn("Successfully registered schema", info_call)
        self.assertIn("logging_test_schema", info_call)

    @patch("rail_django.decorators.logger")
    def test_failed_registration_logging(self, mock_logger):
        """Test du logging lors d'un échec d'enregistrement."""

        # Simuler une erreur
        self.mock_registry.register_schema.side_effect = Exception("Test error")

        @register_schema(name="error_logging_schema")
        class ErrorLoggingSchema:
            pass

        # Vérifier que l'erreur a été loggée
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        self.assertIn("Failed to register schema", error_call)
        self.assertIn("error_logging_schema", error_call)


if __name__ == "__main__":
    unittest.main()

