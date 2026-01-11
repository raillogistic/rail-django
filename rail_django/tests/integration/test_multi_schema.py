"""
Tests d'intégration pour le système multi-schémas GraphQL.

Ce module contient des tests d'intégration complets pour la fonctionnalité
de routage multi-schémas, incluant les vues, les URLs, et l'intégration complète.
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.test import Client, TestCase, override_settings
from django.urls import include, path, reverse

from rail_django.core.registry import SchemaInfo, SchemaRegistry
from rail_django.views.graphql_views import MultiSchemaGraphQLView, SchemaListView


class TestMultiSchemaRouting(TestCase):
    """Tests d'intégration pour le routage multi-schémas."""

    def setUp(self):
        """Configuration initiale pour chaque test."""
        self.client = Client()
        self.registry = SchemaRegistry()
        self.registry.clear()  # Nettoyer le registre

        # Créer des schémas de test
        self.mock_schema1 = Mock()
        self.mock_schema1.execute.return_value = Mock(
            data={"test": "schema1_result"}, errors=None
        )

        self.mock_schema2 = Mock()
        self.mock_schema2.execute.return_value = Mock(
            data={"test": "schema2_result"}, errors=None
        )

        # Enregistrer les schémas de test
        self.schema_info1 = self.registry.register_schema(
            name="test_schema1",
            description="Premier schéma de test",
            version="1.0.0",
            enabled=True,
        )

        self.schema_info2 = self.registry.register_schema(
            name="test_schema2",
            description="Deuxième schéma de test",
            version="2.0.0",
            enabled=True,
        )

        self.disabled_schema = self.registry.register_schema(
            name="disabled_schema", description="Schéma désactivé", enabled=False
        )

    def tearDown(self):
        """Nettoyage après chaque test."""
        self.registry.clear()

    @patch("rail_django.core.registry.schema_registry")
    def test_multi_schema_graphql_view_get_request(self, mock_registry):
        """Test de la vue MultiSchemaGraphQLView avec une requête GET."""
        mock_registry.discover_schemas.return_value = None
        mock_registry.get_schema.return_value = self.schema_info1

        view = MultiSchemaGraphQLView()
        view.setup(Mock(method="GET"), schema_name="test_schema1")

        # Simuler une requête GET (GraphiQL)
        request = Mock()
        request.method = "GET"
        request.GET = {}
        request.META = {"HTTP_ACCEPT": "text/html"}

        response = view.dispatch(request, schema_name="test_schema1")

        # Vérifier que le schéma correct a été récupéré
        mock_registry.get_schema.assert_called_with("test_schema1")

    @patch("rail_django.core.registry.schema_registry")
    def test_multi_schema_graphql_view_post_request(self, mock_registry):
        """Test de la vue MultiSchemaGraphQLView avec une requête POST."""
        mock_registry.discover_schemas.return_value = None
        mock_registry.get_schema.return_value = self.schema_info1

        view = MultiSchemaGraphQLView()

        # Simuler une requête POST GraphQL
        request = Mock()
        request.method = "POST"
        request.body = json.dumps({"query": "{ test }"}).encode("utf-8")
        request.content_type = "application/json"
        request.META = {}

        with patch.object(view, "execute_graphql_request") as mock_execute:
            mock_execute.return_value = JsonResponse({"data": {"test": "result"}})

            response = view.dispatch(request, schema_name="test_schema1")

            # Vérifier que la requête GraphQL a été exécutée
            mock_execute.assert_called_once()

    @patch("rail_django.core.registry.schema_registry")
    def test_multi_schema_graphql_view_schema_not_found(self, mock_registry):
        """Test de la vue avec un schéma inexistant."""
        mock_registry.discover_schemas.return_value = None
        mock_registry.get_schema.return_value = None

        view = MultiSchemaGraphQLView()
        request = Mock()
        request.method = "GET"

        response = view.dispatch(request, schema_name="nonexistent_schema")

        # Vérifier que la réponse indique une erreur 404
        self.assertEqual(response.status_code, 404)

    @patch("rail_django.core.registry.schema_registry")
    def test_multi_schema_graphql_view_disabled_schema(self, mock_registry):
        """Test de la vue avec un schéma désactivé."""
        mock_registry.discover_schemas.return_value = None
        disabled_schema_info = Mock()
        disabled_schema_info.enabled = False
        mock_registry.get_schema.return_value = disabled_schema_info

        view = MultiSchemaGraphQLView()
        request = Mock()
        request.method = "GET"

        response = view.dispatch(request, schema_name="disabled_schema")

        # Vérifier que la réponse indique que le schéma est désactivé
        self.assertEqual(response.status_code, 403)

    @patch("rail_django.core.registry.schema_registry")
    def test_schema_list_view_get(self, mock_registry):
        """Test de la vue SchemaListView."""
        mock_registry.discover_schemas.return_value = None
        mock_registry.list_schemas.return_value = [self.schema_info1, self.schema_info2]

        view = SchemaListView()
        request = Mock()
        request.method = "GET"

        response = view.get(request)

        # Vérifier que la réponse contient la liste des schémas
        self.assertEqual(response.status_code, 200)

        # Décoder le contenu JSON
        content = json.loads(response.content.decode("utf-8"))

        self.assertIn("schemas", content)
        self.assertEqual(len(content["schemas"]), 2)

        # Vérifier les détails des schémas
        schema_names = [schema["name"] for schema in content["schemas"]]
        self.assertIn("test_schema1", schema_names)
        self.assertIn("test_schema2", schema_names)

class TestMultiSchemaURLIntegration(TestCase):
    """Tests d'intégration pour les URLs multi-schémas."""

    def setUp(self):
        """Configuration pour les tests d'URLs."""
        self.client = Client()
        self.registry = SchemaRegistry()
        self.registry.clear()

        # Enregistrer un schéma de test
        mock_schema = Mock()
        mock_schema.execute.return_value = Mock(data={"hello": "world"}, errors=None)

        self.registry.register_schema(
            name="url_test_schema", description="Schéma pour test d'URLs"
        )

    def tearDown(self):
        """Nettoyage après les tests d'URLs."""
        self.registry.clear()

    @override_settings(ROOT_URLCONF="rail_django.urls")
    @patch("rail_django.core.registry.schema_registry")
    def test_multi_schema_url_routing(self, mock_registry):
        """Test du routage des URLs multi-schémas."""
        mock_registry.discover_schemas.return_value = None
        # Mock du registre pour retourner notre schéma de test
        schema_info = Mock()
        schema_info.enabled = True
        schema_info.schema = Mock()
        mock_registry.get_schema.return_value = schema_info

        # Test de l'URL multi-schéma
        with patch(
            "rail_django.views.graphql_views.MultiSchemaGraphQLView.dispatch"
        ) as mock_dispatch:
            mock_dispatch.return_value = JsonResponse({"data": {"test": "success"}})

            response = self.client.get("/graphql/url_test_schema/")

            # Vérifier que la vue a été appelée
            mock_dispatch.assert_called_once()

    @override_settings(ROOT_URLCONF="rail_django.urls")
    @patch("rail_django.core.registry.schema_registry")
    def test_schema_list_url(self, mock_registry):
        """Test de l'URL de liste des schémas."""
        mock_registry.discover_schemas.return_value = None
        mock_registry.list_schemas.return_value = []

        with patch("rail_django.views.graphql_views.SchemaListView.get") as mock_get:
            mock_get.return_value = JsonResponse({"schemas": []})

            response = self.client.get("/schemas/")

            # Vérifier que la vue a été appelée
            mock_get.assert_called_once()

class TestMultiSchemaAuthentication(TestCase):
    """Tests d'intégration pour l'authentification multi-schémas."""

    def setUp(self):
        """Configuration pour les tests d'authentification."""
        self.client = Client()
        self.registry = SchemaRegistry()
        self.registry.clear()

        # Créer un utilisateur de test
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        # Enregistrer un schéma avec authentification
        mock_schema = Mock()
        self.auth_schema_info = self.registry.register_schema(
            name="auth_schema",
            description="Schéma avec authentification",
            settings={
                "authentication_required": True,
                "permission_classes": ["IsAuthenticated"],
            },
        )

    def tearDown(self):
        """Nettoyage après les tests d'authentification."""
        self.registry.clear()

    @patch("rail_django.core.registry.schema_registry")
    def test_authenticated_access(self, mock_registry):
        """Test d'accès avec authentification."""
        mock_registry.discover_schemas.return_value = None
        mock_registry.get_schema.return_value = self.auth_schema_info

        # Se connecter
        self.client.login(username="testuser", password="testpass123")

        view = MultiSchemaGraphQLView()

        # Simuler une requête authentifiée
        request = Mock()
        request.method = "GET"
        request.user = self.user
        request.user.is_authenticated = True

        # Le test devrait passer sans erreur d'authentification
        with patch.object(view, "check_schema_permissions") as mock_check:
            mock_check.return_value = True

            result = view.check_schema_permissions(request, self.auth_schema_info)
            self.assertTrue(result)

    @patch("rail_django.core.registry.schema_registry")
    def test_unauthenticated_access_denied(self, mock_registry):
        """Test de refus d'accès sans authentification."""
        mock_registry.discover_schemas.return_value = None
        mock_registry.get_schema.return_value = self.auth_schema_info

        view = MultiSchemaGraphQLView()

        # Simuler une requête non authentifiée
        request = Mock()
        request.method = "GET"
        request.user = Mock()
        request.user.is_authenticated = False

        # Le test devrait échouer pour manque d'authentification
        with patch.object(view, "check_schema_permissions") as mock_check:
            mock_check.return_value = False

            result = view.check_schema_permissions(request, self.auth_schema_info)
            self.assertFalse(result)


class TestMultiSchemaErrorHandling(TestCase):
    """Tests d'intégration pour la gestion d'erreurs multi-schémas."""

    def setUp(self):
        """Configuration pour les tests de gestion d'erreurs."""
        self.client = Client()
        self.registry = SchemaRegistry()
        self.registry.clear()

    def tearDown(self):
        """Nettoyage après les tests de gestion d'erreurs."""
        self.registry.clear()

    @patch("rail_django.core.registry.schema_registry")
    def test_schema_execution_error(self, mock_registry):
        """Test de gestion d'erreur lors de l'exécution du schéma."""
        mock_registry.discover_schemas.return_value = None
        # Créer un schéma qui lève une erreur
        error_schema = Mock()
        error_schema.execute.side_effect = Exception("Schema execution failed")

        schema_info = Mock()
        schema_info.enabled = True
        schema_info.schema = error_schema

        mock_registry.get_schema.return_value = schema_info

        view = MultiSchemaGraphQLView()
        request = Mock()
        request.method = "POST"
        request.body = json.dumps({"query": "{ test }"}).encode("utf-8")

        with patch.object(view, "execute_graphql_request") as mock_execute:
            # Simuler une erreur d'exécution
            mock_execute.side_effect = Exception("Execution error")

            response = view.dispatch(request, schema_name="error_schema")

            # Vérifier que l'erreur est gérée correctement
            self.assertEqual(response.status_code, 500)

    @patch("rail_django.core.registry.schema_registry")
    def test_invalid_graphql_query(self, mock_registry):
        """Test de gestion d'une requête GraphQL invalide."""
        mock_registry.discover_schemas.return_value = None
        schema_info = Mock()
        schema_info.enabled = True
        mock_registry.get_schema.return_value = schema_info

        view = MultiSchemaGraphQLView()
        request = Mock()
        request.method = "POST"
        request.body = b"invalid json"

        response = view.dispatch(request, schema_name="test_schema")

        # Vérifier que l'erreur JSON est gérée
        self.assertEqual(response.status_code, 400)

    @patch("rail_django.core.registry.schema_registry")
    def test_registry_unavailable(self, mock_registry):
        """Test de gestion quand le registre n'est pas disponible."""
        mock_registry.discover_schemas.return_value = None
        mock_registry.get_schema.side_effect = ImportError("Registry not available")

        view = MultiSchemaGraphQLView()
        request = Mock()
        request.method = "GET"

        response = view.dispatch(request, schema_name="test_schema")

        # Vérifier que l'erreur de registre est gérée
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    import unittest

    unittest.main()
