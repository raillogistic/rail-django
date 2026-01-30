"""
Tests d'intégration pour les points d'entrée API GraphQL.

Ce module teste:
- Les endpoints GraphQL complets
- L'authentification et l'autorisation
- La validation des requêtes et mutations
- La gestion des erreurs API
- Les performances des endpoints
"""

import json
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import graphene
import pytest
from django.conf import settings
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client as DjangoClient
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from graphene import Schema
from rail_django.testing import RailGraphQLTestClient
from graphene_django.views import GraphQLView
from rail_django.core.schema import SchemaBuilder
from rail_django.middleware import GraphQLPerformanceMiddleware
from rail_django.core.rate_limiting import clear_rate_limiter_cache

# Configuration de test pour les endpoints
TEST_GRAPHQL_SETTINGS = {
    "MIDDLEWARE": [
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "corsheaders.middleware.CorsMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        "rail_django.middleware.performance.GraphQLPerformanceMiddleware",
        "rail_django.middleware.auth.GraphQLRateLimitMiddleware",
    ],
    "GRAPHENE": {
        "SCHEMA": "tests.test_integration.test_api_endpoints.test_schema",
        "MIDDLEWARE": [
            "rail_django.middleware.GraphQLPerformanceMiddleware",
            "rail_django.middleware.auth.GraphQLRateLimitMiddleware",
        ],
    },
    "RAIL_DJANGO_GRAPHQL": {
        "schema_settings": {
            "authentication_required": True,
            "permission_classes": [],
            "auto_camelcase": True,
        },
        "type_generation_settings": {
            "auto_camelcase": True,
        },
        "SECURITY": {
            "enable_rate_limiting": True,
            "rate_limit_requests": 10,
            "rate_limit_window": 60,
        },
        "DEVELOPMENT": {
            "verbose_logging": False,
        },
    },
    "RAIL_DJANGO_GRAPHQL_SCHEMAS": {
        "gql": {
            "batch": True,
            "schema_settings": {
                "authentication_required": False,
                "enable_graphiql": False,
                "auto_camelcase": True,
            },
        },
        "secure": {
            "schema_settings": {
                "authentication_required": True,
                "enable_graphiql": False,
                "auto_camelcase": True,
            },
        },
    },
    "CORS_ALLOWED_ORIGINS": [
        "http://localhost:3000",
    ],
    "CORS_ALLOW_METHODS": [
        "GET",
        "POST",
        "OPTIONS",
    ],
    "CORS_ALLOW_HEADERS": [
        "content-type",
        "authorization",
    ],
    "SECURE_CONTENT_TYPE_NOSNIFF": True,
    "X_FRAME_OPTIONS": "DENY",
    "SECURE_BROWSER_XSS_FILTER": True,
    "DEBUG": False,
}


@override_settings(**TEST_GRAPHQL_SETTINGS)
class TestAPIEndpointsIntegration(TestCase):
    """Tests d'intégration pour les endpoints API GraphQL."""

    def setUp(self):
        """Configuration des tests d'endpoints API."""
        from django.core.cache import cache
        cache.clear()
        
        from rail_django.core.registry import schema_registry

        schema_registry.clear()
        clear_rate_limiter_cache()
        # Client Django pour les tests HTTP
        self.django_client = DjangoClient()

        # Créer des utilisateurs de test
        self.admin_user = User.objects.create_user(
            username="admin_test",
            email="admin@example.com",
            password="admin_password",
            is_staff=True,
            is_superuser=True,
        )

        self.regular_user = User.objects.create_user(
            username="user_test", email="user@example.com", password="user_password"
        )

        self.readonly_user = User.objects.create_user(
            username="readonly_test",
            email="readonly@example.com",
            password="readonly_password",
        )

        # Créer des groupes et permissions
        self.admin_group = Group.objects.create(name="Administrateurs")
        self.user_group = Group.objects.create(name="Utilisateurs")
        self.readonly_group = Group.objects.create(name="Lecture seule")

        # Assigner les utilisateurs aux groupes
        self.admin_user.groups.add(self.admin_group)
        self.regular_user.groups.add(self.user_group)
        self.readonly_user.groups.add(self.readonly_group)

        # Générer le schéma de test
        self.schema_generator = SchemaBuilder()
        self.schema = self.schema_generator.get_schema()

        # Client GraphQL
        self.graphql_client = RailGraphQLTestClient(
            self.schema, schema_name="default"
        )

        # URL de l'endpoint GraphQL
        self.graphql_url = "/graphql/gql/"
        self.secure_graphql_url = "/graphql/secure/"

    def test_graphql_endpoint_availability(self):
        """Test la disponibilité de l'endpoint GraphQL."""
        # Test GET sur l'endpoint (GraphiQL interface)
        response = self.django_client.get(self.graphql_url)

        # L'endpoint doit être accessible
        self.assertIn(response.status_code, [200, 405])  # 405 si GET non autorisé

        # Test POST avec une requête simple
        query = {
            "query": """
            query {
                __schema {
                    types {
                        name
                    }
                }
            }
            """
        }

        response = self.django_client.post(
            self.secure_graphql_url,
            data=json.dumps(query),
            content_type="application/json",
        )

        # La requête doit fonctionner
        self.assertEqual(response.status_code, 200)

        # Vérifier que la réponse est du JSON valide
        response_data = json.loads(response.content)
        self.assertIn("data", response_data)

    def test_authentication_required_endpoint(self):
        """Test l'authentification requise sur l'endpoint."""
        query = {
            "query": """
            query {
                users {
                    id
                    username
                    email
                }
            }
            """
        }

        # Requête sans authentification sur l'endpoint sécurisé
        response = self.django_client.post(
            self.secure_graphql_url, data=json.dumps(query), content_type="application/json"
        )

        response_data = json.loads(response.content)

        # Vérifier que l'authentification est requise
        self.assertIn("errors", response_data, "Unauthenticated request should return errors")

        error_messages = [
            error.get("message", "") for error in response_data["errors"]
        ]
        auth_required = any(
            "authentication" in msg.lower()
            or "login" in msg.lower()
            or "unauthorized" in msg.lower()
            or "not authenticated" in msg.lower()
            for msg in error_messages
        )
        self.assertTrue(
            auth_required,
            f"Expected authentication error, got: {error_messages}"
        )

    def test_permission_based_access(self):
        """Test l'accès basé sur les permissions."""
        # Requête de lecture (doit être accessible à tous les utilisateurs connectés)
        read_query = {
            "query": """
            query {
                __schema {
                    queryType {
                        name
                    }
                }
            }
            """
        }

        # Test avec utilisateur en lecture seule
        self.django_client.login(username="readonly_test", password="readonly_password")

        response = self.django_client.post(
            self.graphql_url,
            data=json.dumps(read_query),
            content_type="application/json",
        )

        response_data = json.loads(response.content)

        # La lecture doit être autorisée
        self.assertEqual(response.status_code, 200)
        self.assertIn("data", response_data, "Read query should return data")
        self.assertIsNotNone(response_data["data"])

        # Mutation (doit nécessiter des permissions spéciales)
        mutation_query = {
            "query": """
            mutation {
                createUser(input: {
                    username: "new_user"
                    email: "new@example.com"
                    password: "password123"
                }) {
                    ok
                    object {
                        id
                        username
                    }
                    errors {
                        field
                        message
                    }
                }
            }
            """
        }

        response = self.django_client.post(
            self.graphql_url,
            data=json.dumps(mutation_query),
            content_type="application/json",
        )

        response_data = json.loads(response.content)

        # La mutation doit être refusée pour l'utilisateur en lecture seule
        # Either we get GraphQL errors or the mutation returns success=False
        if "errors" in response_data:
            permission_denied = any(
                "permission" in error.get("message", "").lower()
                or "unauthorized" in error.get("message", "").lower()
                or "forbidden" in error.get("message", "").lower()
                or "not permitted" in error.get("message", "").lower()
                for error in response_data["errors"]
            )
            self.assertTrue(
                permission_denied,
                f"Expected permission denied error for readonly user, got: {response_data['errors']}"
            )
        elif "data" in response_data and response_data["data"]:
            create_result = response_data["data"].get("createUser")
            if create_result:
                # Mutation should fail for readonly user
                self.assertFalse(
                    create_result.get("success", False),
                    "Readonly user should not be able to create users"
                )

    def test_input_validation_endpoint(self):
        """Test la validation des entrées sur l'endpoint."""
        # Requête avec syntaxe GraphQL invalide
        invalid_query = {
            "query": """
            query {
                invalidField {
                    nonExistentField
                }
            }
            """
        }

        self.django_client.login(username="admin_test", password="admin_password")

        response = self.django_client.post(
            self.graphql_url,
            data=json.dumps(invalid_query),
            content_type="application/json",
        )

        response_data = json.loads(response.content)

        # La requête invalide doit retourner une erreur
        self.assertIn("errors", response_data)
        self.assertGreater(len(response_data["errors"]), 0)

        # Test avec JSON malformé
        response = self.django_client.post(
            self.graphql_url,
            data='{"query": "invalid json"',  # JSON malformé
            content_type="application/json",
        )

        # La requête doit retourner une erreur 400
        self.assertEqual(response.status_code, 400)

    def test_error_handling_endpoint(self):
        """Test la gestion des erreurs sur l'endpoint."""
        # Requête qui génère une erreur métier
        error_query = {
            "query": """
            mutation {
                createUser(input: {
                    username: ""
                    email: "invalid-email"
                    password: "123"
                }) {
                    ok
                    object {
                        id
                    }
                    errors {
                        field
                        message
                    }
                }
            }
            """
        }

        self.django_client.login(username="admin_test", password="admin_password")

        response = self.django_client.post(
            self.graphql_url,
            data=json.dumps(error_query),
            content_type="application/json",
        )

        response_data = json.loads(response.content)

        # La réponse doit contenir des erreurs de validation
        if "data" in response_data and response_data["data"]:
            create_result = response_data["data"].get("createUser")
            if create_result:
                # Soit success=False, soit des erreurs
                self.assertTrue(
                    not create_result.get("success", True)
                    or create_result.get("errors")
                )
        elif "errors" in response_data:
            # Erreurs GraphQL directes
            self.assertGreater(len(response_data["errors"]), 0)

    def test_rate_limiting_endpoint(self):
        """Test la limitation de taux sur l'endpoint."""
        query = {
            "query": """
            query {
                __schema {
                    queryType {
                        name
                    }
                }
            }
            """
        }

        self.django_client.login(username="user_test", password="user_password")

        # Effectuer de nombreuses requêtes rapidement (exceed the limit of 10)
        responses = []
        for i in range(15):
            response = self.django_client.post(
                self.graphql_url,
                data=json.dumps(query),
                content_type="application/json",
            )
            responses.append(response)

        # Vérifier si la limitation de taux est active
        rate_limited = any(response.status_code == 429 for response in responses)

        if not rate_limited:
            # Vérifier dans les réponses GraphQL pour rate limit errors
            for response in responses:
                if response.status_code == 200:
                    response_data = json.loads(response.content)
                    if "errors" in response_data:
                        rate_limit_error = any(
                            "rate limit" in error.get("message", "").lower()
                            or "too many requests" in error.get("message", "").lower()
                            for error in response_data["errors"]
                        )
                        if rate_limit_error:
                            rate_limited = True
                            break

        self.assertTrue(
            rate_limited,
            "Rate limiting should trigger after exceeding request limit"
        )

    def test_cors_headers_endpoint(self):
        """Test les en-têtes CORS sur l'endpoint."""
        query = {
            "query": """
            query {
                __schema {
                    queryType {
                        name
                    }
                }
            }
            """
        }

        # Requête avec en-tête Origin
        response = self.django_client.post(
            self.graphql_url,
            data=json.dumps(query),
            content_type="application/json",
            HTTP_ORIGIN="http://localhost:3000",
        )

        # Vérifier les en-têtes CORS
        # At least one CORS header should be present
        cors_header_present = (
            "Access-Control-Allow-Origin" in response
            or "access-control-allow-origin" in {k.lower() for k in response.headers.keys()}
        )

        self.assertTrue(
            cors_header_present,
            "CORS headers should be present in response"
        )

        # Vérifier que l'origine est autorisée
        if "Access-Control-Allow-Origin" in response:
            self.assertIn(
                response["Access-Control-Allow-Origin"],
                ["*", "http://localhost:3000"],
                "CORS should allow the configured origin"
            )

    def test_content_type_handling(self):
        """Test la gestion des types de contenu."""
        query = """
        query {
            __schema {
                queryType {
                    name
                }
            }
        }
        """

        # Test avec application/json
        response = self.django_client.post(
            self.graphql_url,
            data=json.dumps({"query": query}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        # Test avec application/graphql
        response = self.django_client.post(
            self.graphql_url, data=query, content_type="application/graphql"
        )

        # Doit être accepté ou retourner une erreur explicite
        self.assertIn(response.status_code, [200, 400, 415])

        # Test avec multipart/form-data (pour les uploads)
        response = self.django_client.post(
            self.graphql_url, data={"query": query}, content_type="multipart/form-data"
        )

        # Doit être géré ou retourner une erreur explicite
        self.assertIn(response.status_code, [200, 400, 415])

    def test_graphiql_interface(self):
        """Test l'interface GraphiQL."""
        # Requête GET pour l'interface GraphiQL
        response = self.django_client.get(self.graphql_url, HTTP_ACCEPT="text/html")

        # Vérifier que l'interface est disponible
        if response.status_code == 200:
            content = response.content.decode("utf-8")

            # Vérifier que c'est bien l'interface GraphiQL
            graphiql_indicators = ["GraphiQL", "graphql", "query", "mutation"]

            has_graphiql = any(
                indicator in content.lower() for indicator in graphiql_indicators
            )

            if has_graphiql:
                self.assertIn("text/html", response.get("Content-Type", ""))
        else:
            self.skipTest("GraphiQL interface not available")

    def test_batch_queries_endpoint(self):
        """Test les requêtes en lot sur l'endpoint."""
        batch_queries = [
            {
                "query": """
                query {
                    __schema {
                        queryType {
                            name
                        }
                    }
                }
                """
            },
            {
                "query": """
                query {
                    __schema {
                        mutationType {
                            name
                        }
                    }
                }
                """
            },
        ]

        self.django_client.login(username="admin_test", password="admin_password")

        response = self.django_client.post(
            self.graphql_url,
            data=json.dumps(batch_queries),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code, 200,
            "Batch queries endpoint should return 200"
        )

        response_data = json.loads(response.content)

        # La réponse doit être une liste pour les requêtes en lot
        self.assertIsInstance(
            response_data, list,
            "Batch queries should return a list response"
        )
        self.assertEqual(
            len(response_data), 2,
            "Batch response should contain 2 results"
        )

        # Chaque élément doit avoir une structure de réponse GraphQL
        for i, item in enumerate(response_data):
            self.assertTrue(
                "data" in item or "errors" in item,
                f"Batch response item {i} should have 'data' or 'errors'"
            )

    def test_websocket_subscriptions_endpoint(self):
        """Test les souscriptions WebSocket."""
        # Ce test vérifie que subscriptions via HTTP POST sont correctement rejetées
        # et renvoient une erreur appropriée indiquant que WebSocket est requis

        subscription_query = {
            "query": """
            subscription {
                userUpdated {
                    id
                    username
                    email
                }
            }
            """
        }

        self.django_client.login(username="admin_test", password="admin_password")

        response = self.django_client.post(
            self.graphql_url,
            data=json.dumps(subscription_query),
            content_type="application/json",
        )

        response_data = json.loads(response.content)

        # Les souscriptions ne doivent pas fonctionner via HTTP POST
        # Elles doivent retourner une erreur explicative
        self.assertIn(
            "errors", response_data,
            "Subscriptions over HTTP should return an error"
        )

        # Vérifier que l'erreur mentionne les subscriptions ou WebSocket
        error_messages = [
            error.get("message", "").lower() for error in response_data["errors"]
        ]
        subscription_error = any(
            "subscription" in msg
            or "websocket" in msg
            or "not supported" in msg
            for msg in error_messages
        )
        self.assertTrue(
            subscription_error,
            f"Expected subscription/websocket error, got: {error_messages}"
        )

    def test_endpoint_performance(self):
        """Test les performances de l'endpoint."""
        import time

        query = {
            "query": """
            query {
                __schema {
                    types {
                        name
                        fields {
                            name
                            type {
                                name
                            }
                        }
                    }
                }
            }
            """
        }

        self.django_client.login(username="admin_test", password="admin_password")

        # Mesurer le temps de réponse
        start_time = time.time()

        response = self.django_client.post(
            self.graphql_url, data=json.dumps(query), content_type="application/json"
        )

        response_time = time.time() - start_time

        # La réponse doit être rapide (moins de 2 seconde)
        self.assertLess(response_time, 2.0)

        # La requête doit réussir
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertTrue("data" in response_data or "errors" in response_data)

    def test_endpoint_security_headers(self):
        """Test les en-têtes de sécurité sur l'endpoint."""
        query = {
            "query": """
            query {
                __schema {
                    queryType {
                        name
                    }
                }
            }
            """
        }

        response = self.django_client.post(
            self.graphql_url, data=json.dumps(query), content_type="application/json"
        )

        # Vérifier les en-têtes de sécurité recommandés
        security_headers_found = []

        # Check for X-Content-Type-Options
        if "X-Content-Type-Options" in response:
            self.assertEqual(
                response["X-Content-Type-Options"], "nosniff",
                "X-Content-Type-Options should be 'nosniff'"
            )
            security_headers_found.append("X-Content-Type-Options")

        # Check for X-Frame-Options
        if "X-Frame-Options" in response:
            self.assertIn(
                response["X-Frame-Options"], ["DENY", "SAMEORIGIN"],
                "X-Frame-Options should be DENY or SAMEORIGIN"
            )
            security_headers_found.append("X-Frame-Options")

        # Check for X-XSS-Protection
        if "X-XSS-Protection" in response:
            security_headers_found.append("X-XSS-Protection")

        # Check for Content-Security-Policy
        if "Content-Security-Policy" in response:
            security_headers_found.append("Content-Security-Policy")

        # Check for Strict-Transport-Security
        if "Strict-Transport-Security" in response:
            security_headers_found.append("Strict-Transport-Security")

        # At least some security headers should be present
        self.assertGreater(
            len(security_headers_found), 0,
            "At least one security header should be configured. "
            "Expected: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, "
            "Content-Security-Policy, or Strict-Transport-Security"
        )


@pytest.mark.integration
class TestAPIEndpointsAdvanced:
    """Tests d'intégration avancés pour les endpoints API."""

    def test_endpoint_monitoring_metrics(self):
        """Test les métriques de monitoring des endpoints."""
        # Ce test vérifierait l'intégration avec des systèmes de monitoring
        # comme Prometheus, New Relic, etc.
        pass

    def test_endpoint_caching_headers(self):
        """Test les en-têtes de cache sur les endpoints."""
        # Test des en-têtes Cache-Control, ETag, etc.
        pass

    def test_endpoint_compression(self):
        """Test la compression des réponses."""
        # Test de la compression gzip/deflate
        pass

    def test_endpoint_internationalization(self):
        """Test l'internationalisation des endpoints."""
        # Test des en-têtes Accept-Language
        pass

    def test_endpoint_api_versioning(self):
        """Test le versioning de l'API."""
        # Test des différentes versions d'API
        pass


# Configuration du schéma de test
class MockQuery(graphene.ObjectType):
    hello = graphene.String(default_value="Hi!")


class MockMutation(graphene.ObjectType):
    pass


test_schema = Schema(query=MockQuery, mutation=MockMutation)


