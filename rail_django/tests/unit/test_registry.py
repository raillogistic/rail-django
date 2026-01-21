"""
Tests unitaires pour le système de registre de schémas GraphQL.

Ce module contient des tests complets pour la classe SchemaRegistry,
incluant l'enregistrement, la découverte automatique, et la gestion des schémas.
"""

import threading
import time
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

from django.apps import apps
from django.conf import settings
from django.test import TestCase

from rail_django.core.registry import SchemaInfo, SchemaRegistry, schema_registry
from rail_django.core.schema import SchemaBuilder


class TestSchemaInfo(TestCase):
    """Tests pour la classe SchemaInfo."""

    def test_schema_info_creation(self):
        """Test la création d'une instance SchemaInfo."""
        schema_info = SchemaInfo(
            name="test_schema",
            description="Test schema description",
            version="1.0.0",
            apps=["test_app"],
            models=["TestModel"],
            exclude_models=[],
            settings={},
            schema_class=Mock,
            auto_discover=True,
            enabled=True,
        )

        self.assertEqual(schema_info.name, "test_schema")
        self.assertEqual(schema_info.description, "Test schema description")
        self.assertEqual(schema_info.version, "1.0.0")
        self.assertEqual(schema_info.apps, ["test_app"])
        self.assertTrue(schema_info.auto_discover)
        self.assertTrue(schema_info.enabled)

    def test_schema_info_defaults(self):
        """Test les valeurs par défaut de SchemaInfo."""
        schema_info = SchemaInfo(name="minimal_schema")

        self.assertEqual(schema_info.name, "minimal_schema")
        self.assertEqual(schema_info.description, "")
        self.assertEqual(schema_info.version, "1.0.0")
        self.assertEqual(schema_info.apps, [])
        self.assertEqual(schema_info.models, [])
        self.assertEqual(schema_info.exclude_models, [])
        self.assertEqual(schema_info.settings, {})
        self.assertIsNone(schema_info.schema_class)
        self.assertTrue(schema_info.auto_discover)
        self.assertTrue(schema_info.enabled)


class TestSchemaRegistry(TestCase):
    """Tests pour la classe SchemaRegistry."""

    def setUp(self):
        """Configuration initiale pour chaque test."""
        self.registry = SchemaRegistry()
        self.mock_schema = Mock()
        self.mock_builder = Mock()

    def tearDown(self):
        """Nettoyage après chaque test."""
        # Clear the registry
        self.registry._schemas.clear()
        self.registry._schema_builders.clear()

    def test_singleton_pattern(self):
        """Test que SchemaRegistry ne suit PAS le pattern singleton."""
        # SchemaRegistry n'est pas un singleton - chaque instance est indépendante
        registry1 = SchemaRegistry()
        registry2 = SchemaRegistry()
        self.assertIsNot(registry1, registry2)

        # Mais l'instance globale est partagée
        from rail_django.core.registry import schema_registry as global1
        from rail_django.core.registry import schema_registry as global2

        self.assertIs(global1, global2)

    def test_register_schema_basic(self):
        """Test l'enregistrement basique d'un schéma."""
        schema_info = self.registry.register_schema(
            name="test_schema", description="Test schema"
        )

        self.assertIsInstance(schema_info, SchemaInfo)
        self.assertEqual(schema_info.name, "test_schema")
        self.assertEqual(schema_info.description, "Test schema")

        # Vérifier que le schéma est dans le registre
        retrieved_schema = self.registry.get_schema("test_schema")
        self.assertEqual(retrieved_schema, schema_info)

    def test_register_schema_with_builder(self):
        """Test l'enregistrement d'un schéma avec des paramètres avancés."""
        schema_info = self.registry.register_schema(
            name="builder_schema",
            description="Builder schema",
            apps=["test_app"],
            models=["TestModel"],
        )

        self.assertEqual(schema_info.apps, ["test_app"])
        self.assertEqual(schema_info.models, ["TestModel"])
        self.assertEqual(schema_info.name, "builder_schema")
        self.assertEqual(schema_info.description, "Builder schema")

    def test_register_duplicate_schema(self):
        """Test l'enregistrement d'un schéma avec un nom déjà existant."""
        # Premier enregistrement
        self.registry.register_schema(
            name="duplicate_schema", description="First schema"
        )

        # Deuxième enregistrement avec le même nom (should update, not raise error)
        schema_info = self.registry.register_schema(
            name="duplicate_schema", description="Updated schema"
        )

        self.assertEqual(schema_info.description, "Updated schema")

    def test_unregister_schema(self):
        """Test la désenregistrement d'un schéma."""
        # Enregistrer un schéma
        self.registry.register_schema(
            name="temp_schema", description="Temporary schema"
        )

        # Vérifier qu'il est enregistré
        self.assertIsNotNone(self.registry.get_schema("temp_schema"))

        # Désenregistrer
        result = self.registry.unregister_schema("temp_schema")
        self.assertTrue(result)

        # Vérifier qu'il n'est plus dans le registre
        self.assertIsNone(self.registry.get_schema("temp_schema"))

    def test_unregister_nonexistent_schema(self):
        """Test la désenregistrement d'un schéma inexistant."""
        result = self.registry.unregister_schema("nonexistent_schema")
        self.assertFalse(result)

    def test_get_schema(self):
        """Test la récupération d'un schéma par nom."""
        schema_info = self.registry.register_schema(
            name="get_test_schema", description="Test schema"
        )

        retrieved = self.registry.get_schema("get_test_schema")
        self.assertEqual(retrieved, schema_info)

        # Test avec un schéma inexistant
        nonexistent = self.registry.get_schema("nonexistent")
        self.assertIsNone(nonexistent)

    def test_list_schemas(self):
        """Test la liste de tous les schémas."""
        # Enregistrer plusieurs schémas
        schema1 = self.registry.register_schema("schema1", description="Schema 1")
        schema2 = self.registry.register_schema(
            "schema2", description="Schema 2", enabled=False
        )
        schema3 = self.registry.register_schema("schema3", description="Schema 3")

        # Lister tous les schémas
        all_schemas = self.registry.list_schemas()
        self.assertEqual(len(all_schemas), 3)
        self.assertIn(schema1, all_schemas)
        self.assertIn(schema2, all_schemas)
        self.assertIn(schema3, all_schemas)

        # Lister seulement les schémas activés
        enabled_schemas = self.registry.list_schemas(enabled_only=True)
        self.assertEqual(len(enabled_schemas), 2)
        self.assertIn(schema1, enabled_schemas)
        self.assertNotIn(schema2, enabled_schemas)
        self.assertIn(schema3, enabled_schemas)

    def test_get_schema_names(self):
        """Test la récupération des noms de schémas."""
        self.registry.register_schema("name_test1", description="Test 1")
        self.registry.register_schema("name_test2", description="Test 2", enabled=False)
        self.registry.register_schema("name_test3", description="Test 3")

        # Tous les noms
        all_names = self.registry.get_schema_names()
        self.assertEqual(set(all_names), {"name_test1", "name_test2", "name_test3"})

        # Seulement les noms activés
        enabled_names = self.registry.get_schema_names(enabled_only=True)
        self.assertEqual(set(enabled_names), {"name_test1", "name_test3"})

    def test_enable_disable_schema(self):
        """Test l'activation et désactivation de schémas."""
        schema_info = self.registry.register_schema(
            "toggle_schema", description="Toggle test"
        )

        # Initialement activé
        self.assertTrue(schema_info.enabled)

        # Désactiver
        result = self.registry.disable_schema("toggle_schema")
        self.assertTrue(result)
        self.assertFalse(schema_info.enabled)

        # Réactiver
        result = self.registry.enable_schema("toggle_schema")
        self.assertTrue(result)
        self.assertTrue(schema_info.enabled)

        # Test avec schéma inexistant
        self.assertFalse(self.registry.enable_schema("nonexistent"))
        self.assertFalse(self.registry.disable_schema("nonexistent"))

    def test_thread_safety(self):
        """Test la sécurité des threads du registre."""
        results = []
        errors = []

        def register_schemas(thread_id):
            """Fonction pour enregistrer des schémas dans un thread."""
            try:
                for i in range(10):
                    schema_name = f"thread_{thread_id}_schema_{i}"
                    self.registry.register_schema(
                        schema_name, description=f"Thread {thread_id} schema {i}"
                    )
                    results.append(schema_name)
            except Exception as e:
                errors.append(e)

        # Créer plusieurs threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=register_schemas, args=(i,))
            threads.append(thread)

        # Démarrer tous les threads
        for thread in threads:
            thread.start()

        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()

        # Vérifier qu'il n'y a pas d'erreurs
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")

        # Vérifier que tous les schémas ont été enregistrés
        self.assertEqual(len(results), 50)
        self.assertEqual(len(self.registry.list_schemas()), 50)

    @patch("rail_django.core.registry.discovery.apps")
    @patch("rail_django.core.registry.discovery.import_string")
    def test_auto_discover_schemas(self, mock_import_string, mock_apps):
        """Test la découverte automatique de schémas."""
        # Mock des applications Django
        mock_app1 = Mock()
        mock_app1.name = "test_app1"
        mock_app1.path = "/path/to/app1"

        mock_app2 = Mock()
        mock_app2.name = "test_app2"
        mock_app2.path = "/path/to/app2"

        mock_apps.get_app_configs.return_value = [mock_app1, mock_app2]

        # Mock du module schema pour chaque app
        mock_schema_module1 = Mock()
        mock_schema_module1.SCHEMA_CONFIG = {
            "name": "app1_schema",
            "description": "Test app 1 schema",
            "version": "1.0.0",
        }

        mock_schema_module2 = Mock()
        mock_schema_module2.SCHEMA_CONFIG = {
            "name": "app2_schema",
            "description": "Test app 2 schema",
            "version": "1.0.0",
        }

        def import_side_effect(module_path):
            if module_path == "test_app1.graphql_schema":
                return mock_schema_module1
            elif module_path == "test_app2.graphql_schema":
                return mock_schema_module2
            else:
                raise ImportError(f"No module named '{module_path}'")

        mock_import_string.side_effect = import_side_effect

        # Exécuter la découverte automatique
        discovered_count = self.registry.auto_discover_schemas()

        # Vérifier les résultats
        self.assertEqual(discovered_count, 2)
        self.assertIsNotNone(self.registry.get_schema("app1_schema"))
        self.assertIsNotNone(self.registry.get_schema("app2_schema"))

    def test_clear_registry(self):
        """Test le nettoyage complet du registre."""
        # Enregistrer quelques schémas
        self.registry.register_schema("clear_test1", description="Clear test 1")
        self.registry.register_schema("clear_test2", description="Clear test 2")

        # Vérifier qu'ils sont enregistrés
        self.assertEqual(len(self.registry.list_schemas()), 2)

        # Nettoyer le registre
        self.registry.clear()

        # Vérifier que tout est nettoyé
        self.assertEqual(len(self.registry.list_schemas()), 0)

    def test_schema_exists(self):
        """Test la vérification d'existence de schéma."""
        self.assertFalse(self.registry.schema_exists("nonexistent"))

        self.registry.register_schema("exists_test", description="Exists test")
        self.assertTrue(self.registry.schema_exists("exists_test"))

        self.registry.unregister_schema("exists_test")
        self.assertFalse(self.registry.schema_exists("exists_test"))


class TestGlobalSchemaRegistry(TestCase):
    """Tests pour l'instance globale du registre de schémas."""

    def test_global_registry_instance(self):
        """Test que l'instance globale est accessible."""
        from rail_django.core.registry import schema_registry

        self.assertIsInstance(schema_registry, SchemaRegistry)

        # Test que c'est la même instance
        from rail_django.core.registry import schema_registry as registry2

        self.assertIs(schema_registry, registry2)

    def test_global_registry_functionality(self):
        """Test que l'instance globale fonctionne correctement."""
        from rail_django.core.registry import schema_registry

        # Nettoyer d'abord
        schema_registry.clear()

        # Enregistrer un schéma
        mock_schema = Mock()
        schema_info = schema_registry.register_schema("global_test_schema", mock_schema)

        # Vérifier qu'il est accessible
        retrieved = schema_registry.get_schema("global_test_schema")
        self.assertEqual(retrieved, schema_info)

        # Nettoyer après le test
        schema_registry.clear()


if __name__ == "__main__":
    unittest.main()
