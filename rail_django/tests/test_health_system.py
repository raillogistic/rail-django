"""
Tests complets pour le système de surveillance de santé GraphQL.

Ce module teste tous les aspects du système de santé incluant
les endpoints, les vérifications de santé, et le tableau de bord.
"""

import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse

from ..extensions.health import HealthChecker, HealthStatus, SystemMetrics
from ..views.health_views import (
    HealthAPIView,
    HealthDashboardView,
    HealthHistoryView,
    health_check_endpoint,
    health_components_endpoint,
    health_metrics_endpoint,
)


class HealthCheckerTestCase(TestCase):
    """
    Tests pour la classe HealthChecker et ses méthodes.
    """

    def setUp(self):
        """Configuration initiale pour les tests."""
        self.health_checker = HealthChecker()

    def test_health_status_dataclass(self):
        """Test de la dataclass HealthStatus."""
        status = HealthStatus(
            component="test_component",
            status="healthy",
            message="Test message",
            response_time_ms=100.5,
            timestamp=datetime.now(timezone.utc),
        )

        self.assertEqual(status.component, "test_component")
        self.assertEqual(status.status, "healthy")
        self.assertEqual(status.message, "Test message")
        self.assertEqual(status.response_time_ms, 100.5)
        self.assertIsInstance(status.timestamp, datetime)

    def test_system_metrics_dataclass(self):
        """Test de la dataclass SystemMetrics."""
        metrics = SystemMetrics(
            cpu_usage_percent=25.5,
            memory_usage_percent=60.0,
            memory_used_mb=1024.0,
            memory_available_mb=2048.0,
            disk_usage_percent=45.0,
            active_connections=10,
            cache_hit_rate=85.5,
            uptime_seconds=3600,
        )

        self.assertEqual(metrics.cpu_usage_percent, 25.5)
        self.assertEqual(metrics.memory_usage_percent, 60.0)
        self.assertEqual(metrics.active_connections, 10)
        self.assertEqual(metrics.cache_hit_rate, 85.5)

    def test_check_schema_health_success(self):
        """Test de vérification de santé du schéma GraphQL."""
        # Mock the schema returned by get_schema to simulate a healthy introspection
        with patch("rail_django.core.schema.get_schema") as mock_get_schema:
            fake_schema = MagicMock()

            class FakeResult:
                errors = None
                data = {"__schema": {"types": ["Query", "Mutation"]}}

            fake_schema.execute.return_value = FakeResult()
            mock_get_schema.return_value = fake_schema

            result = self.health_checker.check_schema_health()

            self.assertIsInstance(result, HealthStatus)
            self.assertEqual(result.component, "schema")
            self.assertEqual(result.status, "healthy")
            self.assertIsInstance(result.response_time_ms, float)
            self.assertIsInstance(result.timestamp, datetime)

    def test_check_schema_health_failure(self):
        """Test de vérification de santé du schéma avec erreur."""
        with patch("rail_django.core.schema.get_schema") as mock_get_schema:
            mock_get_schema.side_effect = Exception("Schema build failed")

            result = self.health_checker.check_schema_health()

            self.assertIsInstance(result, HealthStatus)
            self.assertEqual(result.status, "unhealthy")
            self.assertIn("Schema build failed", result.message)

    def test_check_database_health_success(self):
        """Test de vérification de santé de la base de données."""
        result = self.health_checker.check_database_health()

        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIsInstance(result[0], HealthStatus)
        self.assertTrue(result[0].component.startswith("database_"))
        self.assertIn(result[0].status, {"healthy", "degraded", "unhealthy"})

    def test_check_database_health_failure(self):
        """Test de vérification de santé de la base de données avec erreur."""
        # Patch the connections mapping used by HealthChecker to simulate a failing cursor
        failing_conn = MagicMock()
        failing_conn.cursor.side_effect = Exception("Database connection failed")

        with patch(
            "rail_django.extensions.health.connections",
            {"default": failing_conn},
        ):
            result = self.health_checker.check_database_health()

            self.assertIsInstance(result, list)
            self.assertEqual(result[0].status, "unhealthy")
            self.assertIn("Database connection failed", result[0].message)

    def test_check_cache_health_success(self):
        """Test de vérification de santé du cache (désactivé)."""
        result = self.health_checker.check_cache_health()

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_check_cache_health_disabled(self):
        """Vérifie que la vérification du cache est désactivée et sûre."""
        result = self.health_checker.check_cache_health()
        self.assertEqual(result, [])

    def test_get_system_metrics(self):
        """Test de récupération des métriques système."""
        with patch("psutil.cpu_percent", return_value=25.5), patch(
            "psutil.virtual_memory"
        ) as mock_memory, patch("psutil.disk_usage") as mock_disk:
            # Configuration des mocks
            mock_memory.return_value = MagicMock(
                percent=60.0,
                used=1024 * 1024 * 1024,  # 1GB en bytes
                available=2048 * 1024 * 1024,  # 2GB en bytes
            )
            # psutil.disk_usage returns an object with used/total attributes
            mock_disk.return_value = MagicMock(
                used=45 * 1024 * 1024,
                total=100 * 1024 * 1024,
            )

            result = self.health_checker.get_system_metrics()

            self.assertIsInstance(result, SystemMetrics)
            self.assertEqual(result.cpu_usage_percent, 25.5)
            self.assertEqual(result.memory_usage_percent, 60.0)
            self.assertGreaterEqual(result.uptime_seconds, 0.0)

    def test_get_health_report(self):
        """Test de génération du rapport de santé complet."""
        with patch.object(
            self.health_checker, "check_schema_health"
        ) as mock_schema, patch.object(
            self.health_checker, "check_database_health"
        ) as mock_db, patch.object(
            self.health_checker, "check_cache_health"
        ) as mock_cache:
            # Configuration des mocks avec objets dataclass
            mock_schema.return_value = HealthStatus(
                component="schema",
                status="healthy",
                message="",
                response_time_ms=10.0,
                timestamp=datetime.now(timezone.utc),
            )
            mock_db.return_value = [
                HealthStatus(
                    component="database_default",
                    status="healthy",
                    message="",
                    response_time_ms=5.0,
                    timestamp=datetime.now(timezone.utc),
                )
            ]
            mock_cache.return_value = [
                HealthStatus(
                    component="cache_default",
                    status="degraded",
                    message="",
                    response_time_ms=2.0,
                    timestamp=datetime.now(timezone.utc),
                )
            ]

            result = self.health_checker.get_health_report()

            self.assertIsInstance(result, dict)
            self.assertEqual(result["overall_status"], "degraded")
            self.assertEqual(result["healthy_components"], 2)
            self.assertEqual(result["degraded_components"], 1)
            self.assertEqual(result["unhealthy_components"], 0)
            self.assertIn("recommendations", result)

    def test_health_report_all_healthy(self):
        """Test du rapport de santé avec tous les composants sains."""
        with patch.object(
            self.health_checker, "check_schema_health"
        ) as mock_schema, patch.object(
            self.health_checker, "check_database_health"
        ) as mock_db, patch.object(
            self.health_checker, "check_cache_health"
        ) as mock_cache:
            # Tous les composants sont sains
            mock_schema.return_value = HealthStatus(
                component="schema",
                status="healthy",
                message="",
                response_time_ms=10.0,
                timestamp=datetime.now(timezone.utc),
            )
            mock_db.return_value = [
                HealthStatus(
                    component="database_default",
                    status="healthy",
                    message="",
                    response_time_ms=5.0,
                    timestamp=datetime.now(timezone.utc),
                )
            ]
            mock_cache.return_value = [
                HealthStatus(
                    component="cache_default",
                    status="healthy",
                    message="",
                    response_time_ms=2.0,
                    timestamp=datetime.now(timezone.utc),
                )
            ]

            result = self.health_checker.get_health_report()

            self.assertEqual(result["overall_status"], "healthy")
            self.assertEqual(result["healthy_components"], 3)
            self.assertEqual(result["degraded_components"], 0)
            self.assertEqual(result["unhealthy_components"], 0)

    def test_health_report_with_unhealthy_components(self):
        """Test du rapport de santé avec des composants défaillants."""
        with patch.object(
            self.health_checker, "check_schema_health"
        ) as mock_schema, patch.object(
            self.health_checker, "check_database_health"
        ) as mock_db, patch.object(
            self.health_checker, "check_cache_health"
        ) as mock_cache:
            # Un composant défaillant
            mock_schema.return_value = HealthStatus(
                component="schema",
                status="unhealthy",
                message="",
                response_time_ms=10.0,
                timestamp=datetime.now(timezone.utc),
            )
            mock_db.return_value = [
                HealthStatus(
                    component="database_default",
                    status="healthy",
                    message="",
                    response_time_ms=5.0,
                    timestamp=datetime.now(timezone.utc),
                )
            ]
            mock_cache.return_value = [
                HealthStatus(
                    component="cache_default",
                    status="degraded",
                    message="",
                    response_time_ms=2.0,
                    timestamp=datetime.now(timezone.utc),
                )
            ]

            result = self.health_checker.get_health_report()

            self.assertEqual(result["overall_status"], "unhealthy")
            self.assertEqual(result["healthy_components"], 1)
            self.assertEqual(result["degraded_components"], 1)
            self.assertEqual(result["unhealthy_components"], 1)


class HealthViewsTestCase(TestCase):
    """
    Tests pour les vues du système de santé.
    """

    def setUp(self):
        """Configuration initiale pour les tests."""
        self.client = Client()

    def test_health_dashboard_view_get(self):
        """Test de la vue du tableau de bord de santé."""
        with patch("rail_django.views.health_views.HealthChecker") as mock_checker:
            mock_instance = mock_checker.return_value
            mock_instance.get_health_report.return_value = {
                "overall_status": "healthy",
                "healthy_components": 3,
            }
            mock_instance.get_system_metrics.return_value = {
                "cpu_usage_percent": 25.0,
                "memory_usage_percent": 60.0,
            }

            response = self.client.get("/health/")

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "GraphQL System Health Dashboard")

    def test_health_api_view_get(self):
        """Test de l'API de santé en GET."""
        with patch("rail_django.views.health_views.HealthChecker") as mock_checker:
            mock_instance = mock_checker.return_value
            mock_instance.get_health_report.return_value = {"overall_status": "healthy"}
            mock_instance.get_system_metrics.return_value = {"cpu_usage_percent": 25.0}
            mock_instance.check_schema_health.return_value = {"status": "healthy"}
            mock_instance.check_database_health.return_value = {"status": "healthy"}
            mock_instance.check_cache_health.return_value = {"status": "healthy"}

            response = self.client.get("/health/api/")

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertIn("health_status", data)
            self.assertIn("system_metrics", data)
            self.assertIn("timestamp", data)

    def test_health_api_view_post_graphql(self):
        """Test de l'API de santé avec requête GraphQL."""
        with patch("rail_django.views.health_views.HealthChecker") as mock_checker:
            mock_instance = mock_checker.return_value
            mock_instance.get_health_report.return_value = {"overall_status": "healthy"}
            mock_instance.get_system_metrics.return_value = {"cpu_usage_percent": 25.0}

            graphql_query = {
                "query": "query { healthStatus systemMetrics }",
                "variables": {},
            }

            response = self.client.post(
                "/health/api/",
                data=json.dumps(graphql_query),
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertIn("data", data)
            self.assertIn("healthStatus", data["data"])
            self.assertIn("systemMetrics", data["data"])

    def test_health_check_endpoint_healthy(self):
        """Test de l'endpoint de vérification simple - système sain."""
        with patch("rail_django.views.health_views.HealthChecker") as mock_checker:
            mock_instance = mock_checker.return_value
            mock_instance.get_health_report.return_value = {
                "overall_status": "healthy",
                "healthy_components": 3,
                "degraded_components": 0,
                "unhealthy_components": 0,
            }

            response = self.client.get("/health/check/")

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(data["status"], "healthy")
            self.assertEqual(data["total_components"], 3)

    def test_health_check_endpoint_unhealthy(self):
        """Test de l'endpoint de vérification simple - système défaillant."""
        with patch("rail_django.views.health_views.HealthChecker") as mock_checker:
            mock_instance = mock_checker.return_value
            mock_instance.get_health_report.return_value = {
                "overall_status": "unhealthy",
                "healthy_components": 1,
                "degraded_components": 1,
                "unhealthy_components": 1,
            }

            response = self.client.get("/health/check/")

            self.assertEqual(response.status_code, 503)  # Service Unavailable
            data = json.loads(response.content)
            self.assertEqual(data["status"], "unhealthy")

    def test_health_metrics_endpoint(self):
        """Test de l'endpoint des métriques système."""
        with patch("rail_django.views.health_views.HealthChecker") as mock_checker:
            mock_instance = mock_checker.return_value
            mock_instance.get_system_metrics.return_value = {
                "cpu_usage_percent": 25.0,
                "memory_usage_percent": 60.0,
                "collection_time_ms": 50,
            }

            response = self.client.get("/health/metrics/")

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertIn("metrics", data)
            self.assertEqual(data["metrics"]["cpu_usage_percent"], 25.0)

    def test_health_components_endpoint(self):
        """Test de l'endpoint du statut des composants."""
        with patch("rail_django.views.health_views.HealthChecker") as mock_checker:
            mock_instance = mock_checker.return_value
            mock_instance.check_schema_health.return_value = {"status": "healthy"}
            mock_instance.check_database_health.return_value = {"status": "healthy"}
            mock_instance.check_cache_health.return_value = {"status": "degraded"}

            response = self.client.get("/health/components/")

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertIn("components", data)
            self.assertEqual(data["total_components"], 3)
            self.assertEqual(data["components"]["schema"]["status"], "healthy")
            self.assertEqual(data["components"]["cache"]["status"], "degraded")

    def test_health_history_view_get(self):
        """Test de la vue d'historique de santé."""
        response = self.client.get("/health/history/")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("history", data)
        self.assertIn("period_hours", data)
        self.assertEqual(data["period_hours"], 24)  # Valeur par défaut

    def test_health_history_view_with_parameters(self):
        """Test de la vue d'historique avec paramètres personnalisés."""
        response = self.client.get("/health/history/?hours=12&interval=10")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["period_hours"], 12)
        self.assertEqual(data["interval_minutes"], 10)

    def test_health_history_view_invalid_parameters(self):
        """Test de la vue d'historique avec paramètres invalides."""
        response = self.client.get("/health/history/?hours=invalid&interval=bad")

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("error", data)
        self.assertIn("Paramètres invalides", data["error"])


class HealthSystemIntegrationTestCase(TestCase):
    """
    Tests d'intégration pour le système de santé complet.
    """

    def setUp(self):
        """Configuration initiale pour les tests d'intégration."""
        self.client = Client()

    def test_full_health_check_workflow(self):
        """Test du workflow complet de vérification de santé."""
        # 1. Vérifier l'endpoint simple
        response = self.client.get("/health/check/")
        self.assertIn(response.status_code, [200, 503])

        # 2. Récupérer les métriques détaillées
        response = self.client.get("/health/metrics/")
        self.assertEqual(response.status_code, 200)

        # 3. Vérifier le statut des composants
        response = self.client.get("/health/components/")
        self.assertEqual(response.status_code, 200)

        # 4. Accéder au tableau de bord
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)

    def test_health_system_under_load(self):
        """Test du système de santé sous charge."""
        # Simuler plusieurs requêtes simultanées
        responses = []

        for _ in range(10):
            response = self.client.get("/health/check/")
            responses.append(response)

        # Vérifier que toutes les requêtes ont été traitées
        for response in responses:
            self.assertIn(response.status_code, [200, 503])

    def test_health_system_error_handling(self):
        """Test de la gestion d'erreurs du système de santé."""
        with patch("rail_django.views.health_views.HealthChecker") as mock_checker:
            mock_checker.side_effect = Exception("System error")

            response = self.client.get("/health/check/")
            self.assertEqual(response.status_code, 503)

            data = json.loads(response.content)
            self.assertEqual(data["status"], "unhealthy")
            self.assertIn("error", data)

    def test_health_dashboard_javascript_integration(self):
        """Test de l'intégration JavaScript du tableau de bord."""
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # Vérifier la présence des éléments JavaScript essentiels
        self.assertIn("refreshData()", content)
        self.assertIn("Chart.js", content)
        self.assertIn("autoRefreshInterval", content)
        self.assertIn("healthHistory", content)

    def test_health_api_graphql_integration(self):
        """Test de l'intégration GraphQL de l'API de santé."""
        # Test avec une requête GraphQL valide
        valid_query = {
            "query": """
                query {
                    healthStatus {
                        overallStatus
                        healthyComponents
                    }
                    systemMetrics {
                        cpuUsagePercent
                        memoryUsagePercent
                    }
                }
            """
        }

        response = self.client.post(
            "/health/api/",
            data=json.dumps(valid_query),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("data", data)

    def test_health_monitoring_performance(self):
        """Test des performances du système de monitoring."""
        start_time = time.time()

        # Effectuer plusieurs vérifications de santé
        for _ in range(5):
            response = self.client.get("/health/check/")
            self.assertIn(response.status_code, [200, 503])

        end_time = time.time()
        total_time = end_time - start_time

        # Vérifier que les vérifications sont rapides (< 5 secondes pour 5 requêtes)
        self.assertLess(total_time, 5.0)

    def test_health_system_caching(self):
        """Test du système de cache pour les vérifications de santé."""
        # Première requête (devrait mettre en cache)
        response1 = self.client.get("/health/metrics/")
        self.assertEqual(response1.status_code, 200)

        # Deuxième requête immédiate (devrait utiliser le cache)
        response2 = self.client.get("/health/metrics/")
        self.assertEqual(response2.status_code, 200)

        # Les réponses devraient être cohérentes
        data1 = json.loads(response1.content)
        data2 = json.loads(response2.content)

        # Vérifier la structure des données
        self.assertIn("metrics", data1)
        self.assertIn("metrics", data2)


if __name__ == "__main__":
    import unittest

    unittest.main()
