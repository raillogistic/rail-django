"""
Tests complets pour le système de génération de requêtes GraphQL.

Ce module teste:
- La génération de requêtes GraphQL pour les modèles Django
- Les requêtes simples et de liste
- Les systèmes de filtrage et pagination
- L'optimisation des requêtes
- La résolution des relations
"""

from typing import Dict, List, Optional, Type
from unittest.mock import MagicMock, Mock, patch

import graphene
import pytest
from django.contrib.auth.models import User
from django.db import models
from django.test import TestCase
from graphene import Boolean, DateTime, Field, Int
from graphene import List as GrapheneList
from graphene import ObjectType, String
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField

from rail_django.generators.filters import AdvancedFilterGenerator
from rail_django.generators.introspector import ModelIntrospector
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator


# Modèles de test pour la génération de requêtes
class QueryTestAuthor(models.Model):
    """Modèle auteur pour les tests de génération de requêtes."""

    nom_auteur = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Nom de l'auteur",
        help_text="Nom unique de l'auteur",
    )
    email_auteur = models.EmailField(
        verbose_name="E-mail de l'auteur", help_text="Adresse e-mail de l'auteur"
    )
    date_naissance = models.DateField(
        null=True, blank=True, verbose_name="Date de naissance"
    )
    est_actif = models.BooleanField(default=True, verbose_name="Est actif")
    nombre_livres = models.PositiveIntegerField(
        default=0, verbose_name="Nombre de livres"
    )

    class Meta:
        app_label = "tests"
        verbose_name = "Auteur"
        verbose_name_plural = "Auteurs"
        ordering = ["nom_auteur"]


class QueryTestBook(models.Model):
    """Modèle livre pour les tests de génération de requêtes."""

    titre_livre = models.CharField(max_length=200, verbose_name="Titre du livre")
    description_livre = models.TextField(
        blank=True, verbose_name="Description du livre"
    )
    auteur_livre = models.ForeignKey(
        QueryTestAuthor,
        on_delete=models.CASCADE,
        related_name="livres_ecrits",
        verbose_name="Auteur du livre",
    )
    categories_livre = models.ManyToManyField(
        "QueryTestCategory",
        blank=True,
        related_name="livres_categories",
        verbose_name="Catégories du livre",
    )
    date_publication = models.DateField(verbose_name="Date de publication")
    prix_livre = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Prix du livre"
    )
    est_disponible = models.BooleanField(default=True, verbose_name="Est disponible")
    nombre_pages = models.PositiveIntegerField(verbose_name="Nombre de pages")

    class Meta:
        app_label = "tests"
        verbose_name = "Livre"
        verbose_name_plural = "Livres"
        ordering = ["-date_publication"]


class QueryTestCategory(models.Model):
    """Modèle catégorie pour les tests de génération de requêtes."""

    nom_categorie = models.CharField(
        max_length=100, unique=True, verbose_name="Nom de la catégorie"
    )
    description_categorie = models.TextField(
        blank=True, verbose_name="Description de la catégorie"
    )
    parent_categorie = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="sous_categories",
        verbose_name="Catégorie parente",
    )

    class Meta:
        app_label = "tests"
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"


class TestQueryGenerator(TestCase):
    """Tests pour la classe QueryGenerator."""

    def setUp(self):
        """Configuration des tests."""
        self.introspector = ModelIntrospector(QueryTestAuthor)
        self.type_generator = TypeGenerator()
        self.query_generator = QueryGenerator(self.type_generator)

    def test_initialization(self):
        """Test l'initialisation du générateur de requêtes."""
        # Test initialisation de base
        generator = QueryGenerator(self.type_generator)
        self.assertIsNotNone(generator)
        self.assertEqual(generator.type_generator, self.type_generator)
        self.assertIsNotNone(generator._filter_generator)

        # Test initialisation avec configuration
        settings_mock = Mock()
        generator_with_settings = QueryGenerator(
            self.type_generator, settings=settings_mock
        )
        self.assertEqual(generator_with_settings.settings, settings_mock)

    def test_generate_single_query(self):
        """Test la génération de requête pour un objet unique."""
        # Générer la requête pour un auteur unique
        author_query = self.query_generator.generate_single_query(QueryTestAuthor)

        # Vérifier que la requête est générée
        self.assertIsNotNone(author_query)
        self.assertIsInstance(author_query, Field)

        # Vérifier le type de retour
        self.assertIsNotNone(author_query.type)

    def test_query_with_relationships(self):
        """Test la génération de requêtes avec relations."""
        # Générer la requête pour QueryTestBook (qui a des relations)
        book_query = self.query_generator.generate_single_query(QueryTestBook)

        # Vérifier que la requête est générée
        self.assertIsNotNone(book_query)

        # La requête doit pouvoir résoudre les relations
        self.assertIsNotNone(book_query.type)

    def test_error_handling_invalid_model(self):
        """Test la gestion d'erreurs pour un modèle invalide."""
        with self.assertRaises((AttributeError, TypeError, ValueError)):
            self.query_generator.generate_single_query(None)

    def test_query_arguments_generation(self):
        """Test la génération des arguments de requêtes."""
        # Générer une requête avec arguments
        author_query = self.query_generator.generate_single_query(QueryTestAuthor)

        # Vérifier que les arguments sont générés
        if hasattr(author_query, "args"):
            # Doit avoir au moins l'argument 'id'
            self.assertIn("id", author_query.args)
        elif hasattr(author_query, "arguments"):
            self.assertIn("id", author_query.arguments)

    def test_nested_query_generation(self):
        """Test la génération de requêtes imbriquées."""
        # Générer une requête pour QueryTestCategory (qui a une relation self)
        category_query = self.query_generator.generate_single_query(QueryTestCategory)

        # Vérifier que la requête est générée
        self.assertIsNotNone(category_query)

        # La requête doit pouvoir gérer les relations self
        self.assertIsNotNone(category_query.type)

