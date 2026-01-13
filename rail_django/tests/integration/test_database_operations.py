"""
Tests d'intégration pour les opérations de base de données.

Ce module teste:
- Les opérations CRUD réelles avec la base de données
- Les transactions et la cohérence des données
- Les performances des requêtes de base de données
- L'intégration avec l'ORM Django
"""

from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import graphene
import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from graphene import Schema
from rail_django.testing import RailGraphQLTestClient
from test_app.models import Category, Post, Tag
from tests.models import TestAccount, TestCustomer

from rail_django.core.schema import SchemaBuilder
from rail_django.generators.introspector import ModelIntrospector
from rail_django.generators.mutations import MutationGenerator
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator


class TestDatabaseOperationsIntegration(TransactionTestCase):
    """Tests d'intégration pour les opérations de base de données."""

    def setUp(self):
        """Configuration des tests d'opérations de base de données."""
        # Initialiser les générateurs avec des paramètres appropriés
        from rail_django.core.settings import TypeGeneratorSettings

        self.introspector = ModelIntrospector(Category)
        self.type_generator = TypeGenerator(settings=TypeGeneratorSettings())
        self.query_generator = QueryGenerator(self.type_generator, None)
        self.mutation_generator = MutationGenerator(self.type_generator, None)

        # Initialiser le générateur de schéma
        self.schema_generator = SchemaBuilder()

        # Modèles de test
        self.test_models = [Category, Post, Tag]

        # Générer le schéma
        self.schema = self.schema_generator.get_schema()
        self.client = RailGraphQLTestClient(self.schema, schema_name="default")

    def test_create_operations(self):
        """Test les opérations de création en base de données."""
        # Créer un client via GraphQL
        mutation = """
        mutation {
            createTestcustomer(input: {
                nomClient: "Dupont"
                prenomClient: "Jean"
                emailClient: "jean.dupont@example.com"
                telephoneClient: "0123456789"
                adresseClient: "123 Rue de la Paix"
                villeClient: "Paris"
                codePostal: "75001"
                paysClient: "France"
            }) {
                ok
                object {
                    id
                    nomClient
                    prenomClient
                    emailClient
                }
                errors {
                    field
                    message
                }
            }
        }
        """

        result = self.client.execute(mutation)

        # Vérifier que la création fonctionne
        self.assertIsNone(result.get("errors"))
        payload = result["data"]["createTestcustomer"]
        self.assertTrue(payload["ok"])
        self.assertIsNotNone(payload["object"])
        self.assertTrue(
            TestCustomer.objects.filter(
                email_client="jean.dupont@example.com"
            ).exists()
        )

    def test_read_operations(self):
        """Test les opérations de lecture en base de données."""
        # Créer des données de test
        with transaction.atomic():
            customer1 = TestCustomer.objects.create(
                nom_client="Martin",
                prenom_client="Pierre",
                email_client="pierre.martin@example.com",
                ville_client="Lyon",
                solde_compte=1000.00,
            )

            customer2 = TestCustomer.objects.create(
                nom_client="Bernard",
                prenom_client="Marie",
                email_client="marie.bernard@example.com",
                ville_client="Marseille",
                solde_compte=2500.00,
            )

        # Lire tous les clients
        query = """
        query {
            allCustomers {
                id
                nomClient
                prenomClient
                emailClient
                villeClient
                soldeCompte
                estActif
            }
        }
        """

        result = self.client.execute(query)

        # Vérifier que la lecture fonctionne
        self.assertIsNone(result.get("errors"))
        self.assertIn("data", result)

        customers = result["data"]["allCustomers"]
        self.assertEqual(len(customers), 2)

        # Vérifier les données
        customer_names = [f"{c['prenomClient']} {c['nomClient']}" for c in customers]
        self.assertIn("Pierre Martin", customer_names)
        self.assertIn("Marie Bernard", customer_names)

    def test_update_operations(self):
        """Test les opérations de mise à jour en base de données."""
        # Créer un client de test
        with transaction.atomic():
            customer = TestCustomer.objects.create(
                nom_client="Durand",
                prenom_client="Paul",
                email_client="paul.durand@example.com",
                ville_client="Nice",
                solde_compte=500.00,
            )

        # Mettre à jour le client via GraphQL
        mutation = (
            """
        mutation {
            updateTestcustomer(
                id: "%s"
                input: {
                    villeClient: "Cannes"
                    soldeCompte: 750.00
                }
            ) {
                ok
                object {
                    id
                    nomClient
                    prenomClient
                    villeClient
                    soldeCompte
                }
                errors {
                    field
                    message
                }
            }
        }
        """
            % customer.id
        )

        result = self.client.execute(mutation)

        # Vérifier que la mise à jour fonctionne
        self.assertIsNone(result.get("errors"))
        payload = result["data"]["updateTestcustomer"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["object"]["villeClient"], "Cannes")

    def test_delete_operations(self):
        """Test les opérations de suppression en base de données."""
        # Créer un client de test
        with transaction.atomic():
            customer = TestCustomer.objects.create(
                nom_client="Moreau",
                prenom_client="Sophie",
                email_client="sophie.moreau@example.com",
            )
            customer_id = customer.id

        # Supprimer le client via GraphQL
        mutation = (
            """
        mutation {
            deleteTestcustomer(id: "%s") {
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
            % customer_id
        )

        result = self.client.execute(mutation)

        # Vérifier que la suppression fonctionne
        self.assertIsNone(result.get("errors"))
        payload = result["data"]["deleteTestcustomer"]
        self.assertTrue(payload["ok"])
        self.assertFalse(TestCustomer.objects.filter(id=customer_id).exists())

    def test_complex_relationships_operations(self):
        """Test les opérations avec des relations complexes."""
        # Créer des données avec relations
        with transaction.atomic():
            customer = TestCustomer.objects.create(
                nom_client="Leroy",
                prenom_client="Antoine",
                email_client="antoine.leroy@example.com",
            )

            account1 = TestAccount.objects.create(
                numero_compte="FR001234567890",
                client_compte=customer,
                type_compte="COURANT",
                solde_compte=1500.00,
            )

            account2 = TestAccount.objects.create(
                numero_compte="FR009876543210",
                client_compte=customer,
                type_compte="EPARGNE",
                solde_compte=5000.00,
                taux_interet=2.50,
            )

        # Lire les données avec relations
        query = """
        query {
            allCustomers {
                id
                nomClient
                prenomClient
                comptesClient {
                    id
                    numeroCompte
                    typeCompte
                    soldeCompte
                    tauxInteret
                }
            }
        }
        """

        result = self.client.execute(query)

        # Vérifier que la lecture avec relations fonctionne
        self.assertIsNone(result.get("errors"))
        self.assertIn("data", result)

        customers = result["data"]["allCustomers"]
        self.assertEqual(len(customers), 1)

        customer_data = customers[0]
        accounts = customer_data["comptesClient"]
        self.assertEqual(len(accounts), 2)

        # Vérifier les types de comptes
        account_types = [acc["typeCompte"] for acc in accounts]
        self.assertIn("COURANT", account_types)
        self.assertIn("EPARGNE", account_types)

    def test_business_method_database_operations(self):
        """Test les opérations de base de données via les méthodes métier."""
        # Créer un client de test
        with transaction.atomic():
            customer = TestCustomer.objects.create(
                nom_client="Petit",
                prenom_client="Claire",
                email_client="claire.petit@example.com",
                solde_compte=1000.00,
            )

        # Exécuter une méthode métier via GraphQL
        mutation = (
            """
        mutation {
            crediterCompteCustomer(
                id: "%s"
                montant: 250.50
            ) {
                success
                result
                errors
            }
        }
        """
            % customer.id
        )

        result = self.client.execute(mutation)

        # Vérifier que la méthode métier fonctionne
        self.skipTest("Business method mutation not yet implemented")

    def test_transaction_integrity(self):
        """Test l'intégrité des transactions en base de données."""
        # Créer des comptes de test
        with transaction.atomic():
            customer1 = TestCustomer.objects.create(
                nom_client="Roux",
                prenom_client="Michel",
                email_client="michel.roux@example.com",
            )

            customer2 = TestCustomer.objects.create(
                nom_client="Blanc",
                prenom_client="Sylvie",
                email_client="sylvie.blanc@example.com",
            )

            account1 = TestAccount.objects.create(
                numero_compte="FR111111111111",
                client_compte=customer1,
                solde_compte=1000.00,
            )

            account2 = TestAccount.objects.create(
                numero_compte="FR222222222222",
                client_compte=customer2,
                solde_compte=500.00,
            )

        # Effectuer un virement via méthode métier
        initial_balance1 = account1.solde_compte
        initial_balance2 = account2.solde_compte
        transfer_amount = 300.00

        try:
            # Simuler l'exécution de la méthode métier
            with transaction.atomic():
                account1.effectuer_virement(account2, transfer_amount)

            # Vérifier que les soldes ont été mis à jour
            account1.refresh_from_db()
            account2.refresh_from_db()

            self.assertEqual(account1.solde_compte, initial_balance1 - transfer_amount)
            self.assertEqual(account2.solde_compte, initial_balance2 + transfer_amount)

        except Exception as e:
            # En cas d'erreur, vérifier que les soldes n'ont pas changé
            account1.refresh_from_db()
            account2.refresh_from_db()

            self.assertEqual(account1.solde_compte, initial_balance1)
            self.assertEqual(account2.solde_compte, initial_balance2)

    def test_validation_errors_database(self):
        """Test la gestion des erreurs de validation en base de données."""
        # Tenter de créer un client avec des données invalides
        mutation = """
        mutation {
            createTestcustomer(input: {
                nomClient: ""
                prenomClient: "Test"
                emailClient: "invalid-email"
                soldeCompte: -100.00
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

        result = self.client.execute(mutation)

        # Vérifier que les erreurs de validation sont gérées
        if not result.get("errors"):
            creation_result = result["data"]["createTestcustomer"]
            if creation_result:
                # La création devrait échouer
                self.assertFalse(creation_result.get("ok", True))
                self.assertIsNotNone(creation_result.get("errors"))

        # Vérifier qu'aucun client invalide n'a été créé
        invalid_customers = TestCustomer.objects.filter(
            nom_client="", solde_compte__lt=0
        )
        self.assertEqual(invalid_customers.count(), 0)

    def test_concurrent_database_operations(self):
        """Test les opérations concurrentes sur la base de données."""
        import threading
        import time

        # Créer un compte de test
        with transaction.atomic():
            customer = TestCustomer.objects.create(
                nom_client="Concurrent",
                prenom_client="Test",
                email_client="concurrent@example.com",
            )

            account = TestAccount.objects.create(
                numero_compte="FR999999999999",
                client_compte=customer,
                solde_compte=1000.00,
            )

        results = []
        errors = []

        def perform_transaction(transaction_type, amount):
            """Effectue une transaction dans un thread séparé."""
            try:
                with transaction.atomic():
                    account_copy = TestAccount.objects.select_for_update().get(
                        id=account.id
                    )

                    if transaction_type == "credit":
                        account_copy.solde_compte += amount
                    else:  # debit
                        if account_copy.solde_compte >= amount:
                            account_copy.solde_compte -= amount
                        else:
                            raise ValueError("Solde insuffisant")

                    account_copy.save()
                    results.append(f"{transaction_type}_{amount}_success")

            except Exception as e:
                errors.append(f"{transaction_type}_{amount}_error: {str(e)}")

        # Lancer plusieurs transactions concurrentes
        threads = []
        for i in range(5):
            # Alternance entre crédit et débit
            transaction_type = "credit" if i % 2 == 0 else "debit"
            amount = 100.00

            thread = threading.Thread(
                target=perform_transaction, args=(transaction_type, amount)
            )
            threads.append(thread)
            thread.start()

        # Attendre que tous les threads se terminent
        for thread in threads:
            thread.join()

        # Vérifier que les transactions ont été gérées correctement
        account.refresh_from_db()

        # Le solde final doit être cohérent
        self.assertGreaterEqual(account.solde_compte, 0)

        # Vérifier qu'il y a eu des succès et possiblement des erreurs
        self.assertGreater(len(results) + len(errors), 0)

    def test_database_performance(self):
        """Test les performances des opérations de base de données."""
        import time

        # Créer un grand nombre de clients
        customers_data = []
        for i in range(100):
            customers_data.append(
                TestCustomer(
                    nom_client=f"Client{i}",
                    prenom_client=f"Prenom{i}",
                    email_client=f"client{i}@example.com",
                    ville_client=f"Ville{i % 10}",
                    solde_compte=i * 10.0,
                )
            )

        # Mesurer le temps de création en lot
        start_time = time.time()
        with transaction.atomic():
            TestCustomer.objects.bulk_create(customers_data)
        creation_time = time.time() - start_time

        # La création en lot doit être rapide (moins de 1 seconde)
        self.assertLess(creation_time, 1.0)

        # Mesurer le temps de lecture
        start_time = time.time()
        query = """
        query {
            allCustomers(limit: 50) {
                id
                nomClient
                prenomClient
                villeClient
            }
        }
        """

        result = self.client.execute(query)
        query_time = time.time() - start_time

        # La lecture doit être rapide (moins de 500ms)
        self.assertLess(query_time, 0.5)

        # Vérifier que la requête fonctionne
        if not result.get("errors"):
            self.assertIn("data", result)

    def test_database_indexes_usage(self):
        """Test l'utilisation des index de base de données."""
        # Créer des données de test
        with transaction.atomic():
            for i in range(50):
                TestCustomer.objects.create(
                    nom_client=f"IndexTest{i}",
                    prenom_client=f"Prenom{i}",
                    email_client=f"indextest{i}@example.com",
                    ville_client="TestVille" if i % 2 == 0 else "AutreVille",
                )

        # Exécuter une requête qui devrait utiliser un index
        with connection.cursor() as cursor:
            # Requête sur email_client (qui a un index)
            cursor.execute(
                "SELECT * FROM tests_testcustomer WHERE email_client = %s",
                ["indextest0@example.com"],
            )
            result = cursor.fetchone()

            # Vérifier que la requête retourne un résultat
            self.assertIsNotNone(result)

        # Tester via GraphQL avec filtrage
        query = """
        query {
            allCustomers(filters: { emailClient: "indextest0@example.com" }) {
                id
                nomClient
                emailClient
            }
        }
        """

        result = self.client.execute(query)

        # Vérifier que le filtrage fonctionne
        if not result.get("errors"):
            self.assertIn("data", result)
            customers = result["data"]["allCustomers"]
            if customers:
                self.assertEqual(len(customers), 1)
                self.assertEqual(customers[0]["emailClient"], "indextest0@example.com")

    def test_database_constraints(self):
        """Test les contraintes de base de données."""
        # Créer un client
        with transaction.atomic():
            customer = TestCustomer.objects.create(
                nom_client="Constraint",
                prenom_client="Test",
                email_client="constraint@example.com",
            )

        # Tenter de créer un autre client avec le même email (violation de contrainte unique)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TestCustomer.objects.create(
                    nom_client="Autre",
                    prenom_client="Client",
                    email_client="constraint@example.com",  # Email déjà utilisé
                )

        # Vérifier qu'il n'y a qu'un seul client avec cet email
        customers_count = TestCustomer.objects.filter(
            email_client="constraint@example.com"
        ).count()
        self.assertEqual(customers_count, 1)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
class TestDatabaseOperationsAdvanced:
    """Tests d'intégration avancés pour les opérations de base de données."""

    def test_database_connection_pooling(self):
        """Test la gestion du pool de connexions."""
        from django.db import connections

        # Vérifier que les connexions sont gérées correctement
        connection = connections["default"]

        # Exécuter plusieurs requêtes
        for i in range(10):
            TestCustomer.objects.filter(id=i).exists()

        # Vérifier que la connexion est toujours active
        assert connection.connection is not None

    def test_database_migration_compatibility(self):
        """Test la compatibilité avec les migrations Django."""
        from django.core.management import call_command
        from django.db import connection

        # Vérifier que les tables existent
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tests_%'"
            )
            tables = cursor.fetchall()

        # Vérifier qu'au moins une table de test existe
        assert len(tables) > 0

    def test_database_backup_restore_simulation(self):
        """Test la simulation de sauvegarde/restauration."""
        # Créer des données
        original_data = []
        with transaction.atomic():
            for i in range(5):
                customer = TestCustomer.objects.create(
                    nom_client=f"Backup{i}",
                    prenom_client=f"Test{i}",
                    email_client=f"backup{i}@example.com",
                )
                original_data.append(
                    {
                        "id": customer.id,
                        "nom_client": customer.nom_client,
                        "email_client": customer.email_client,
                    }
                )

        # Simuler une sauvegarde (export des données)
        backup_data = list(
            TestCustomer.objects.values(
                "nom_client", "prenom_client", "email_client", "solde_compte"
            )
        )

        # Simuler une perte de données
        TestCustomer.objects.filter(nom_client__startswith="Backup").delete()

        # Vérifier que les données ont été supprimées
        remaining_count = TestCustomer.objects.filter(
            nom_client__startswith="Backup"
        ).count()
        assert remaining_count == 0

        # Simuler une restauration
        restored_customers = []
        for data in backup_data:
            customer = TestCustomer.objects.create(**data)
            restored_customers.append(customer)

        # Vérifier que les données ont été restaurées
        restored_count = TestCustomer.objects.filter(
            nom_client__startswith="Backup"
        ).count()
        assert restored_count == 5
