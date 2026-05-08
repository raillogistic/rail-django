"""
Tests for GenericRelation support in the rail-django framework.

This module validates:
- Type generation for models with GenericRelation fields
- GraphQL resolver generation (list, count, stats)
- Query optimizer detection of GenericRelation for prefetch_related
- End-to-end resolver execution with real database objects
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import graphene
import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from rail_django.generators.introspector import ModelIntrospector
from rail_django.generators.types import TypeGenerator
from test_app.models import Attachment, Post, Product, Category


# ---------------------------------------------------------------------------
# Type generation tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenericRelationTypeGeneration(TestCase):
    """Validates that GraphQL types include fields for GenericRelation."""

    def setUp(self):
        """Initialise a fresh TypeGenerator for each test."""
        ModelIntrospector.clear_cache()
        self.type_generator = TypeGenerator()

    def test_generic_relation_list_field_generated(self):
        """GenericRelation should produce a List field on the GraphQL type."""
        product_type = self.type_generator.generate_object_type(Product)
        fields = product_type._meta.fields

        self.assertIn("attachments", fields)

    def test_generic_relation_count_field_generated(self):
        """GenericRelation should produce a _count Int field."""
        product_type = self.type_generator.generate_object_type(Product)
        fields = product_type._meta.fields

        self.assertIn("attachments_count", fields)

    def test_generic_relation_stats_field_generated(self):
        """GenericRelation should produce a _stats aggregate field."""
        product_type = self.type_generator.generate_object_type(Product)
        fields = product_type._meta.fields

        self.assertIn("attachments_stats", fields)

    def test_generic_relation_stats_has_total_count(self):
        """The stats type should always include total_count."""
        product_type = self.type_generator.generate_object_type(Product)
        stats_field = product_type._meta.fields.get("attachments_stats")
        self.assertIsNotNone(stats_field)
        stats_type = stats_field.type
        if hasattr(stats_type, "of_type"):
            stats_type = stats_type.of_type
        stats_fields = stats_type._meta.fields
        self.assertIn("total_count", stats_fields)

    def test_generic_relation_on_post_model(self):
        """GenericRelation should also work on the Post model."""
        post_type = self.type_generator.generate_object_type(Post)
        fields = post_type._meta.fields

        self.assertIn("attachments", fields)
        self.assertIn("attachments_count", fields)
        self.assertIn("attachments_stats", fields)

    def test_generic_relation_resolver_exists(self):
        """The generated type should have a resolve_<field_name> method."""
        product_type = self.type_generator.generate_object_type(Product)

        self.assertTrue(hasattr(product_type, "resolve_attachments"))
        self.assertTrue(hasattr(product_type, "resolve_attachments_count"))
        self.assertTrue(hasattr(product_type, "resolve_attachments_stats"))

    def test_generic_relation_does_not_appear_in_reverse_relations(self):
        """GenericRelation names should NOT be duplicated in regular reverse relations."""
        reverse_relations = self.type_generator._get_reverse_relations(Product)
        # "attachments" should not appear in normal reverse relations
        self.assertNotIn("attachments", reverse_relations)

    def test_generic_relations_discovered(self):
        """_get_generic_relations should return the GenericRelation fields."""
        generic_relations = self.type_generator._get_generic_relations(Product)
        self.assertIn("attachments", generic_relations)
        self.assertEqual(generic_relations["attachments"]["model"], Attachment)


# ---------------------------------------------------------------------------
# Query optimizer tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenericRelationQueryOptimizer(TestCase):
    """Validates query optimizer handles GenericRelation correctly."""

    def test_analyzer_resolves_generic_relation_segment(self):
        """_resolve_relation_segment should resolve GenericRelation field names."""
        from rail_django.extensions.optimization.analyzer import QueryAnalyzer
        from rail_django.extensions.optimization.config import QueryOptimizationConfig

        analyzer = QueryAnalyzer(QueryOptimizationConfig())
        relation, related_model = analyzer._resolve_relation_segment(
            Product, "attachments"
        )

        self.assertIsNotNone(relation)
        self.assertEqual(related_model, Attachment)

    def test_analyzer_prefetch_detects_generic_relation(self):
        """_get_prefetch_related_fields should detect GenericRelation fields."""
        from rail_django.extensions.optimization.analyzer import QueryAnalyzer
        from rail_django.extensions.optimization.config import QueryOptimizationConfig

        analyzer = QueryAnalyzer(QueryOptimizationConfig())
        requested_fields = {"attachments", "attachments__id", "attachments__name"}
        prefetch_fields = analyzer._get_prefetch_related_fields(
            Product, requested_fields
        )

        self.assertIn("attachments", prefetch_fields)

    def test_analyzer_does_not_select_related_generic_relation(self):
        """select_related should NOT include GenericRelation (not a FK/O2O)."""
        from rail_django.extensions.optimization.analyzer import QueryAnalyzer
        from rail_django.extensions.optimization.config import QueryOptimizationConfig

        analyzer = QueryAnalyzer(QueryOptimizationConfig())
        requested_fields = {"attachments", "attachments__id"}
        select_fields = analyzer._get_select_related_fields(
            Product, requested_fields
        )

        self.assertNotIn("attachments", select_fields)

    def test_optimizer_resolves_generic_relation_model(self):
        """_resolve_related_model should resolve GenericRelation fields."""
        from rail_django.extensions.optimization.optimizer import QueryOptimizer
        from rail_django.extensions.optimization.config import QueryOptimizationConfig

        optimizer = QueryOptimizer(QueryOptimizationConfig())
        related_model = optimizer._resolve_related_model(Product, "attachments")

        self.assertEqual(related_model, Attachment)

    def test_optimizer_builds_prefetch_for_generic_relation(self):
        """_build_prefetch_objects should handle GenericRelation as plain string."""
        from rail_django.extensions.optimization.optimizer import QueryOptimizer
        from rail_django.extensions.optimization.config import QueryOptimizationConfig

        optimizer = QueryOptimizer(QueryOptimizationConfig())
        prefetch_objects = optimizer._build_prefetch_objects(
            Product, ["attachments"]
        )

        # GenericRelation should produce a plain string, not a Prefetch object
        self.assertEqual(len(prefetch_objects), 1)
        self.assertEqual(prefetch_objects[0], "attachments")

    def test_optimizer_validates_generic_relation_path(self):
        """_is_valid_prefetch_path should accept GenericRelation paths."""
        from rail_django.extensions.optimization.optimizer import QueryOptimizer
        from rail_django.extensions.optimization.config import QueryOptimizationConfig

        optimizer = QueryOptimizer(QueryOptimizationConfig())
        self.assertTrue(optimizer._is_valid_prefetch_path(Product, "attachments"))


# ---------------------------------------------------------------------------
# End-to-end resolver tests (require DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGenericRelationResolverExecution(TestCase):
    """End-to-end tests executing GenericRelation resolvers with real data."""

    def setUp(self):
        """Create test data with generic relations."""
        ModelIntrospector.clear_cache()
        self.type_generator = TypeGenerator()
        self.category = Category.objects.create(name="Test Category", description="")
        self.product = Product.objects.create(
            name="Test Product",
            price=Decimal("99.99"),
            cost_price=Decimal("10.00"),
            inventory_count=10,
            category=self.category,
        )
        self.product_ct = ContentType.objects.get_for_model(Product)

        # Create attachments via GenericRelation
        self.attachment1 = Attachment.objects.create(
            name="photo.jpg",
            file_path="/uploads/photo.jpg",
            content_type=self.product_ct,
            object_id=self.product.pk,
        )
        self.attachment2 = Attachment.objects.create(
            name="manual.pdf",
            file_path="/uploads/manual.pdf",
            content_type=self.product_ct,
            object_id=self.product.pk,
        )

    def test_resolver_returns_correct_attachments(self):
        """The resolver should return only attachments for the correct object."""
        product_type = self.type_generator.generate_object_type(Product)
        resolver = getattr(product_type, "resolve_attachments")
        info = SimpleNamespace(context=SimpleNamespace())

        result = list(resolver(self.product, info))
        self.assertEqual(len(result), 2)
        names = {att.name for att in result}
        self.assertIn("photo.jpg", names)
        self.assertIn("manual.pdf", names)

    def test_count_resolver_returns_correct_count(self):
        """The count resolver should return the correct number."""
        product_type = self.type_generator.generate_object_type(Product)
        resolver = getattr(product_type, "resolve_attachments_count")
        info = SimpleNamespace(context=SimpleNamespace())

        count = resolver(self.product, info)
        self.assertEqual(count, 2)

    def test_stats_resolver_returns_total_count(self):
        """The stats resolver should return correct total_count."""
        product_type = self.type_generator.generate_object_type(Product)
        resolver = getattr(product_type, "resolve_attachments_stats")
        info = SimpleNamespace(context=SimpleNamespace())

        stats = resolver(self.product, info)
        self.assertEqual(stats["total_count"], 2)

    def test_resolver_does_not_leak_across_objects(self):
        """Attachments should NOT leak across different parent objects."""
        # Create another product with different attachments
        other_product = Product.objects.create(
            name="Other Product",
            price=Decimal("49.99"),
            cost_price=Decimal("5.00"),
            inventory_count=5,
            category=self.category,
        )
        Attachment.objects.create(
            name="other.txt",
            content_type=self.product_ct,
            object_id=other_product.pk,
        )

        product_type = self.type_generator.generate_object_type(Product)
        resolver = getattr(product_type, "resolve_attachments")
        info = SimpleNamespace(context=SimpleNamespace())

        # Original product should still have only 2
        result = list(resolver(self.product, info))
        self.assertEqual(len(result), 2)

        # Other product should have only 1
        result_other = list(resolver(other_product, info))
        self.assertEqual(len(result_other), 1)
        self.assertEqual(result_other[0].name, "other.txt")

    def test_resolver_does_not_leak_across_content_types(self):
        """Attachments should NOT leak across different content types."""
        # Create a post with an attachment
        post = Post.objects.create(title="Test Post", category=self.category)
        post_ct = ContentType.objects.get_for_model(Post)
        Attachment.objects.create(
            name="post_attachment.txt",
            content_type=post_ct,
            object_id=post.pk,
        )

        product_type = self.type_generator.generate_object_type(Product)
        resolver = getattr(product_type, "resolve_attachments")
        info = SimpleNamespace(context=SimpleNamespace())

        # Product should still only see its own attachments
        result = list(resolver(self.product, info))
        self.assertEqual(len(result), 2)
        names = {att.name for att in result}
        self.assertNotIn("post_attachment.txt", names)

    def test_resolver_uses_prefetch_cache(self):
        """The resolver should use _prefetched_objects_cache when available."""
        product_type = self.type_generator.generate_object_type(Product)
        resolver = getattr(product_type, "resolve_attachments")
        info = SimpleNamespace(context=SimpleNamespace())

        # Simulate prefetch cache
        sentinel = [Mock(name="cached_attachment")]
        self.product._prefetched_objects_cache = {"attachments": sentinel}

        result = resolver(self.product, info)
        self.assertIs(result, sentinel)

        # Cleanup
        del self.product._prefetched_objects_cache

    def test_prefetch_related_works_with_generic_relation(self):
        """Django's prefetch_related should work correctly with GenericRelation."""
        products = Product.objects.prefetch_related("attachments").filter(
            pk=self.product.pk
        )
        product = products.first()

        # Verify prefetch cache is populated
        self.assertIn("attachments", product._prefetched_objects_cache)
        cached = product._prefetched_objects_cache["attachments"]
        self.assertEqual(len(cached), 2)

    def test_no_column_does_not_exist_error(self):
        """
        Regression test: Querying generic relations should NOT produce
        'column does not exist' errors. This was the original bug where
        the framework tried to use select_related or regular JOINs for
        GenericRelation, which fails because GenericForeignKey fields
        (content_type_id, object_id) live on the *related* table.
        """
        # This should NOT raise any database error
        products = Product.objects.prefetch_related("attachments").all()
        for product in products:
            # Accessing the prefetched data should work
            attachments = list(product.attachments.all())
            self.assertIsInstance(attachments, list)
