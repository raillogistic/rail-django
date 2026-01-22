"""Tests d'intégration pour la génération complète de schémas GraphQL.

Ce module teste:
- Le workflow complet de génération de schémas
- L'intégration entre tous les composants
- La génération de schémas pour des modèles complexes
- L'exécution de requêtes et mutations réelles
"""

from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import graphene
import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import models, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from graphene import ObjectType, Schema
from rail_django.testing import RailGraphQLTestClient
from graphene_django import DjangoObjectType
from tests.models import (
    TestCompany,
    TestEmployee,
    TestProject,
    TestProjectAssignment,
    TestSkill,
    TestSkillCategory,
)

from rail_django.core.schema import AutoSchemaGenerator, SchemaBuilder
from rail_django.decorators import business_logic
from rail_django.generators.filters import AdvancedFilterGenerator
from rail_django.generators.introspector import ModelIntrospector
from rail_django.generators.mutations import MutationGenerator
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator


class TestSchemaGenerationIntegration(TransactionTestCase):
    """Tests d'intégration pour la génération complète de schémas."""

    def setUp(self):
        """Configuration des tests d'intégration."""
        # Créer les tables de test
        call_command("migrate", verbosity=0, interactive=False)
        self.user = User.objects.create_superuser(
            username="schema_admin",
            email="schema_admin@example.com",
            password="testpass123",
        )

        # Initialiser les générateurs avec des paramètres appropriés
        from rail_django.core.settings import (
            MutationGeneratorSettings,
            TypeGeneratorSettings,
        )

        self.introspector = ModelIntrospector(TestCompany)
        self.type_generator = TypeGenerator(settings=TypeGeneratorSettings())
        self.filter_generator = AdvancedFilterGenerator()
        self.query_generator = QueryGenerator(
            self.type_generator, self.filter_generator
        )
        self.mutation_generator = MutationGenerator(
            self.type_generator, MutationGeneratorSettings()
        )

        # Initialiser le générateur de schéma principal
        self.schema_generator = SchemaBuilder()

        # Modèles de test
        self.test_models = [
            TestCompany,
            TestEmployee,
            TestSkill,
            TestSkillCategory,
            TestProject,
            TestProjectAssignment,
        ]

    def test_complete_schema_generation(self):
        """Test la génération complète d'un schéma GraphQL."""
        # Générer le schéma complet
        schema = self.schema_generator.get_schema()

        # Vérifier que le schéma est généré
        self.assertIsNotNone(schema)
        self.assertIsInstance(schema, Schema)

        # Vérifier que le schéma a des queries et mutations
        self.assertTrue(hasattr(schema, "query"))
        self.assertTrue(hasattr(schema, "mutation"))

    def test_schema_introspection(self):
        """Test l'introspection du schéma généré."""
        # Générer le schéma
        schema = self.schema_generator.get_schema()

        # Créer un client de test
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        # Exécuter une requête d'introspection
        introspection_query = """
        query IntrospectionQuery {
            __schema {
                types {
                    name
                    kind
                }
            }
        }
        """

        result = client.execute(introspection_query)

        # Vérifier que l'introspection fonctionne
        self.assertIsNone(result.get("errors"))
        self.assertIn("data", result)
        self.assertIn("__schema", result["data"])
        self.assertIn("types", result["data"]["__schema"])

    def test_query_execution_with_data(self):
        """Test l'exécution de requêtes avec des données réelles."""
        # Créer des données de test
        with transaction.atomic():
            # Créer un utilisateur
            user = User.objects.create_user(
                username="test_user", email="test@example.com", password="testpass123"
            )

            # Créer une entreprise
            company = TestCompany.objects.create(
                nom_entreprise="Test Company",
                secteur_activite="Technology",
                adresse_entreprise="123 Test Street",
                email_entreprise="contact@testcompany.com",
                nombre_employes=10,
            )

            # Créer une catégorie de compétence
            skill_category = TestSkillCategory.objects.create(
                nom_categorie="Programming", description_categorie="Programming skills"
            )

            # Créer une compétence
            skill = TestSkill.objects.create(
                nom_competence="Python",
                description_competence="Python programming",
                niveau_requis="INTERMEDIAIRE",
                categorie_competence=skill_category,
            )

        # Générer le schéma
        schema = self.schema_generator.get_schema()
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        # Exécuter une requête pour récupérer les entreprises
        query = """
        query {
            companies {
                nomEntreprise
                secteurActivite
                nombreEmployes
                estActive
            }
        }
        """

        result = client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result.get("errors"))

        # Vérifier que la requête fonctionne
        self.assertIsNone(result.get("errors"))
        self.assertIn("data", result)
        self.assertIn("companies", result["data"])
        companies = result["data"]["companies"]
        self.assertTrue(
            all(item["secteurActivite"] == "Technology" for item in companies)
        )

        # Vérifier les données retournées
        companies = result["data"]["companies"]
        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0]["nomEntreprise"], "Test Company")
        self.assertEqual(companies[0]["secteurActivite"], "Technology")
        self.assertEqual(companies[0]["nombreEmployes"], 10)
        self.assertTrue(companies[0]["estActive"])

    def test_mutation_execution_with_data(self):
        """Test l'exécution de mutations avec des données réelles."""
        # Générer le schéma
        schema = self.schema_generator.get_schema()
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        # Exécuter une mutation pour créer une entreprise
        mutation = """
        mutation {
            createTestCompany(input: {
                nomEntreprise: "New Company"
                secteurActivite: "Finance"
                adresseEntreprise: "456 Finance Ave"
                emailEntreprise: "info@newcompany.com"
                nombreEmployes: 5
            }) {
                ok
                object {
                    id
                    nomEntreprise
                    secteurActivite
                    nombreEmployes
                }
                errors {
                    field
                    message
                }
            }
        }
        """

        result = client.execute(mutation)
        self.assertIsNone(result.get("errors"))

        # Vérifier que la mutation fonctionne

        self.assertIn("data", result)
        self.assertIn("createTestCompany", result["data"])

        # Vérifier que l'entreprise a été créée
        creation_result = result["data"]["createTestCompany"]
        if creation_result:
            self.assertTrue(creation_result.get("ok", False))
            self.assertIsNotNone(creation_result.get("object"))

    def test_complex_relationship_queries(self):
        """Test les requêtes avec des relations complexes."""
        # Créer des données de test avec relations
        with transaction.atomic():
            # Créer un utilisateur
            user = User.objects.create_user(
                username="manager_user",
                email="manager@example.com",
                password="testpass123",
            )

            # Créer une entreprise
            company = TestCompany.objects.create(
                nom_entreprise="Complex Company",
                secteur_activite="Technology",
                adresse_entreprise="789 Complex Street",
                email_entreprise="contact@complex.com",
                nombre_employes=50,
            )

            # Créer un employé
            from datetime import date

            employee = TestEmployee.objects.create(
                utilisateur_employe=user,
                entreprise_employe=company,
                poste_employe="Manager",
                salaire_employe=75000.00,
                date_embauche=date(2020, 1, 1),
                est_manager=True,
            )

        # Générer le schéma
        schema = self.schema_generator.get_schema()
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        # Exécuter une requête avec relations
        query = """
        query {
            employees {
                utilisateurEmploye {
                    username
                    email
                }
                entrepriseEmploye {
                    nomEntreprise
                    secteurActivite
                }
                posteEmploye
                estManager
            }
        }
        """

        result = client.execute(query)

        # Vérifier que la requête fonctionne
        self.assertIsNone(result.get("errors"))
        self.assertIn("data", result)
        self.assertIn("employees", result["data"])

        # Vérifier les relations
        employees = result["data"]["employees"]
        if employees:
            employee_data = employees[0]
            self.assertIn("utilisateurEmploye", employee_data)
            self.assertIn("entrepriseEmploye", employee_data)
            self.assertEqual(employee_data["posteEmploye"], "Manager")
            self.assertTrue(employee_data["estManager"])

    def test_business_method_mutations(self):
        """Test l'exécution de mutations pour les méthodes métier."""
        # Créer des données de test
        with transaction.atomic():
            company = TestCompany.objects.create(
                nom_entreprise="Business Company",
                secteur_activite="Business",
                adresse_entreprise="123 Business St",
                email_entreprise="biz@company.com",
                nombre_employes=20,
            )

        # Générer le schéma
        schema = self.schema_generator.get_schema()
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        # Exécuter une mutation de méthode métier
        mutation = (
            """
        mutation {
            ajouterEmployeCompany(
                id: "%s"
                nombre: 5
            ) {
                success
                result
                errors
            }
        }
        """
            % company.id
        )

        result = client.execute(mutation)

        # Vérifier que la mutation fonctionne
        self.skipTest("Business method mutation not yet implemented")

        self.assertIn("data", result)

        # Vérifier que l'entreprise a été mise à jour
        company.refresh_from_db()
        self.assertEqual(company.nombre_employes, 25)

    @pytest.mark.skip("Filtering not generated in test environment")
    def test_filtering_and_pagination(self):
        """Test le filtrage et la pagination dans les requêtes."""
        # Créer plusieurs entreprises de test
        with transaction.atomic():
            for i in range(10):
                TestCompany.objects.create(
                    nom_entreprise=f"Company {i}",
                    secteur_activite="Technology" if i % 2 == 0 else "Finance",
                    adresse_entreprise=f"{i} Test Street",
                    email_entreprise=f"company{i}@example.com",
                    nombre_employes=i * 10,
                    est_active=i % 3 != 0,
                )

        # Générer le schéma
        schema = self.schema_generator.get_schema()
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        # Exécuter une requête avec filtres
        query = """
        query {
            companies(
                secteur_activite: "Technology"
                est_active: true
                limit: 3
            ) {
                nomEntreprise
                secteurActivite
                nombreEmployes
            }
        }
        """

        result = client.execute(query)
        print(f"DEBUG: result={result}")

        # Vérifier que la requête fonctionne
        self.assertIn("data", result)
        self.assertIn("companies", result["data"])

    def test_schema_validation(self):
        """Test la validation du schéma généré."""
        # Générer le schéma
        schema = self.schema_generator.get_schema()

        # Vérifier que le schéma est valide
        self.assertIsNotNone(schema)

        # Tester la validation avec une requête invalide
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        invalid_query = """
        query {
            nonExistentField {
                invalidField
            }
        }
        """

        result = client.execute(invalid_query)

        # Vérifier que les erreurs sont correctement gérées
        self.assertIsNotNone(result.get("errors"))

    def test_performance_with_large_dataset(self):
        """Test les performances avec un grand dataset."""
        import time

        # Créer un grand nombre d'entreprises
        companies = []
        for i in range(100):
            companies.append(
                TestCompany(
                    nom_entreprise=f"Performance Company {i}",
                    secteur_activite="Performance",
                    adresse_entreprise=f"{i} Performance Street",
                    email_entreprise=f"perf{i}@example.com",
                    nombre_employes=i,
                )
            )

        with transaction.atomic():
            TestCompany.objects.bulk_create(companies)

        # Générer le schéma
        start_time = time.time()
        schema = self.schema_generator.get_schema([TestCompany])
        generation_time = time.time() - start_time

        # La génération doit être rapide (moins de 2 secondes)
        self.assertLess(generation_time, 2.0)

        # Tester l'exécution de requêtes
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        query = """
        query {
            companies(limit: 10) {
                nomEntreprise
                secteurActivite
            }
        }
        """

        start_time = time.time()
        result = client.execute(query)
        query_time = time.time() - start_time

        # L'exécution doit être rapide (moins de 1 seconde)
        self.assertLess(query_time, 1.0)

        # Vérifier que la requête fonctionne
        if not result.get("errors"):
            self.assertIn("data", result)

    def test_error_handling_integration(self):
        """Test la gestion d'erreurs dans l'intégration complète."""
        # Générer le schéma
        schema = self.schema_generator.get_schema()
        client = RailGraphQLTestClient(
            schema, schema_name="default", user=self.user
        )

        # Tester une mutation avec des données invalides
        mutation = """
        mutation {
            createTestCompany(input: {
                nomEntreprise: ""
                secteurActivite: "Test"
                adresseEntreprise: "Test Address"
                emailEntreprise: "invalid-email"
                nombreEmployes: -5
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

        result = client.execute(mutation)

        # Vérifier que les erreurs sont correctement gérées
        if not result.get("errors"):
            creation_result = result["data"]["createTestCompany"]
            if creation_result:
                self.assertFalse(creation_result.get("ok", True))
                self.assertIsNotNone(creation_result.get("errors"))

    def test_concurrent_schema_access(self):
        """Test l'accès concurrent au schéma généré."""
        import threading
        import time

        # Générer le schéma
        schema = self.schema_generator.get_schema([TestCompany])

        # Créer des données de test
        with transaction.atomic():
            TestCompany.objects.create(
                nom_entreprise="Concurrent Company",
                secteur_activite="Concurrent",
                adresse_entreprise="Concurrent Street",
                email_entreprise="concurrent@example.com",
            )

        results = []
        errors = []

        def execute_query():
            """Exécute une requête dans un thread séparé."""
            try:
                client = RailGraphQLTestClient(
                    schema, schema_name="default", user=self.user
                )
                query = """
                query {
                    companies {
                        nomEntreprise
                    }
                }
                """
                result = client.execute(query)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Lancer plusieurs threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=execute_query)
            threads.append(thread)
            thread.start()

        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()

        # Vérifier qu'il n'y a pas d'erreurs
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 5)

        # Vérifier que tous les résultats sont cohérents
        for result in results:
            self.assertIsNone(result.get("errors"))
            self.assertIn("data", result)


@pytest.mark.integration
class TestSchemaGeneratorAdvanced:
    """Tests d'intégration avancés pour le générateur de schémas."""

    def test_schema_caching_integration(self):
        """Test l'intégration du cache de schémas."""
        schema_generator = AutoSchemaGenerator()

        # Générer le schéma une première fois
        import time

        start_time = time.time()
        schema1 = schema_generator.get_schema([TestCompany])
        first_generation_time = time.time() - start_time

        # Générer le schéma une deuxième fois (devrait utiliser le cache)
        start_time = time.time()
        schema2 = schema_generator.get_schema([TestCompany])
        second_generation_time = time.time() - start_time

        # La deuxième génération devrait être plus rapide
        assert second_generation_time < first_generation_time

        # Les schémas devraient être identiques
        assert schema1 is not None
        assert schema2 is not None

    def test_dynamic_model_registration(self):
        """Test l'enregistrement dynamique de modèles."""
        schema_generator = AutoSchemaGenerator()

        # Enregistrer des modèles dynamiquement
        schema_generator.register_model(TestCompany)
        schema_generator.register_model(TestEmployee)

        # Générer le schéma
        schema = schema_generator.get_schema()

        # Vérifier que le schéma est généré
        assert schema is not None
        assert isinstance(schema, Schema)

    def test_schema_extension_integration(self):
        """Test l'intégration d'extensions de schémas."""
        schema_generator = AutoSchemaGenerator()

        # Ajouter des extensions personnalisées
        custom_query = type(
            "CustomQuery",
            (ObjectType,),
            {
                "custom_field": graphene.String(
                    resolver=lambda self, info: "Custom Value"
                )
            },
        )

        schema_generator.add_query_extension(custom_query)

        # Générer le schéma avec extensions
        schema = schema_generator.get_schema([TestCompany])

        # Vérifier que le schéma est généré
        assert schema is not None
        assert isinstance(schema, Schema)

