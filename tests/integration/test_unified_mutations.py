"""
Integration tests for unified relation input mutations.
"""

import pytest
from django.test import TestCase
from unittest.mock import Mock

from test_app.models import Category, Product, Tag, Post, Comment


def grant_permissions(user, model_perms):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    for model, perms in model_perms.items():
        ct = ContentType.objects.get_for_model(model)
        for codename in perms:
            perm = Permission.objects.get(codename=codename, content_type=ct)
            user.user_permissions.add(perm)


def create_info(user):
    from django.http import HttpRequest

    req = Mock(spec=HttpRequest)
    req.user = user
    req.META = {}

    info = Mock()
    info.context = req
    return info


@pytest.mark.integration
class TestUnifiedMutations(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from rail_django.generators.types import TypeGenerator
        from rail_django.generators.mutations import MutationGenerator
        from rail_django.core.settings import MutationGeneratorSettings

        self.user = User.objects.create_user("testuser", "test@example.com", "pass")
        grant_permissions(
            self.user,
            {
                Category: ["add_category", "change_category", "delete_category"],
                Product: ["add_product", "change_product", "delete_product"],
                Tag: ["add_tag", "change_tag", "delete_tag"],
                Post: ["add_post", "change_post", "delete_post"],
                Comment: ["add_comment", "change_comment", "delete_comment"],
            },
        )

        self.settings = MutationGeneratorSettings()
        self.type_gen = TypeGenerator(mutation_settings=self.settings)
        self.mut_gen = MutationGenerator(self.type_gen, settings=self.settings)

    def test_create_fk_unified_connect(self):
        """Test creating a Product with FK category using connect."""
        cat = Category.objects.create(name="Existing Cat")

        mutation = self.mut_gen.generate_create_mutation(Product)

        # Product has nullable FK to Category
        # Unified input: category: { connect: "ID" }
        input_data = {
            "name": "New Product",
            "price": 10.0,
            "category": {"connect": str(cat.id)},
        }

        info = create_info(self.user)
        res = mutation.mutate(None, info, input=input_data)

        if res.errors:
            print(res.errors)
        self.assertTrue(res.ok)
        self.assertEqual(res.object.category.id, cat.id)

    def test_create_fk_unified_create(self):
        """Test creating a Product with a new nested Category."""
        mutation = self.mut_gen.generate_create_mutation(Product)

        input_data = {
            "name": "Prod with New Cat",
            "price": 20.0,
            "category": {"create": {"name": "New Unified Cat"}},
        }

        info = create_info(self.user)
        res = mutation.mutate(None, info, input=input_data)

        if res.errors:
            print(res.errors)
        self.assertTrue(res.ok)
        self.assertEqual(res.object.category.name, "New Unified Cat")

    def test_create_fk_without_relation(self):
        """Test creating a Product without category (nullable FK)."""
        mutation = self.mut_gen.generate_create_mutation(Product)

        input_data = {
            "name": "Product No Cat",
            "price": 15.0,
        }

        info = create_info(self.user)
        res = mutation.mutate(None, info, input=input_data)

        if res.errors:
            print(res.errors)
        self.assertTrue(res.ok)
        self.assertIsNone(res.object.category)

    def test_create_m2m_unified(self):
        """Test creating Post with M2M tags using connect and create."""
        tag1 = Tag.objects.create(name="Tag1")
        # Ensure category exists for Post (required FK)
        cat = Category.objects.create(name="Post Cat")

        mutation = self.mut_gen.generate_create_mutation(Post)

        # Post has M2M tags
        input_data = {
            "title": "Tagged Post",
            "category": {"connect": str(cat.id)},
            "tags": {"connect": [str(tag1.id)], "create": [{"name": "Tag2"}]},
        }

        info = create_info(self.user)
        res = mutation.mutate(None, info, input=input_data)

        if res.errors:
            print(res.errors)
        self.assertTrue(res.ok)
        self.assertEqual(res.object.tags.count(), 2)
        self.assertTrue(res.object.tags.filter(name="Tag1").exists())
        self.assertTrue(res.object.tags.filter(name="Tag2").exists())

    def test_create_reverse_unified(self):
        """Test creating Category with nested Posts via reverse relation."""
        mutation = self.mut_gen.generate_create_mutation(Category)

        input_data = {
            "name": "Blog Cat",
            "posts": {
                "create": [
                    {"title": "Post 1", "tags": {"create": [{"name": "Tag1"}]}},
                    {"title": "Post 2"},
                ]
            },
        }

        info = create_info(self.user)
        res = mutation.mutate(None, info, input=input_data)

        if res.errors:
            print(res.errors)
        self.assertTrue(res.ok)
        self.assertEqual(res.object.posts.count(), 2)
        post1 = res.object.posts.get(title="Post 1")
        self.assertTrue(post1.tags.filter(name="Tag1").exists())

    def test_update_fk_unified_connect(self):
        """Test updating Product FK with connect to different Category."""
        cat1 = Category.objects.create(name="Cat1")
        cat2 = Category.objects.create(name="Cat2")
        product = Product.objects.create(name="Product", price=10.0, category=cat1)

        mutation = self.mut_gen.generate_update_mutation(Product)

        input_data = {
            "category": {"connect": str(cat2.id)},
        }

        info = create_info(self.user)
        res = mutation.mutate(None, info, id=str(product.id), input=input_data)

        if res.errors:
            print(res.errors)
        self.assertTrue(res.ok)
        self.assertEqual(res.object.category.id, cat2.id)

    def test_update_fk_unified_disconnect(self):
        """Test updating Product FK to disconnect (set to null)."""
        cat = Category.objects.create(name="Cat")
        product = Product.objects.create(name="Product", price=10.0, category=cat)

        mutation = self.mut_gen.generate_update_mutation(Product)

        # Disconnect sets FK to None
        input_data = {
            "category": {"disconnect": True},
        }

        info = create_info(self.user)
        res = mutation.mutate(None, info, id=str(product.id), input=input_data)

        if res.errors:
            print(res.errors)
        self.assertTrue(res.ok)
        product.refresh_from_db()
        self.assertIsNone(res.object.category)

    def test_update_m2m_unified(self):
        """Test updating Post M2M with disconnect and connect."""
        tag1 = Tag.objects.create(name="Tag1")
        tag2 = Tag.objects.create(name="Tag2")
        cat = Category.objects.create(name="Cat")
        post = Post.objects.create(title="My Post", category=cat)
        post.tags.add(tag1)

        mutation = self.mut_gen.generate_update_mutation(Post)

        # Unified update: disconnect Tag1, connect Tag2
        input_data = {"tags": {"disconnect": [str(tag1.id)], "connect": [str(tag2.id)]}}

        info = create_info(self.user)
        res = mutation.mutate(None, info, id=str(post.id), input=input_data)

        self.assertTrue(res.ok)
        self.assertEqual(res.object.tags.count(), 1)
        self.assertTrue(res.object.tags.filter(name="Tag2").exists())
        self.assertFalse(res.object.tags.filter(name="Tag1").exists())

    def test_update_m2m_set_unified(self):
        """Test updating Post M2M with set (replace all)."""
        tag1 = Tag.objects.create(name="Tag1")
        tag2 = Tag.objects.create(name="Tag2")
        cat = Category.objects.create(name="Cat")
        post = Post.objects.create(title="My Post", category=cat)
        post.tags.add(tag1)

        mutation = self.mut_gen.generate_update_mutation(Post)

        # Unified update: set to [Tag2] (replaces Tag1)
        input_data = {"tags": {"set": [str(tag2.id)]}}

        info = create_info(self.user)
        res = mutation.mutate(None, info, id=str(post.id), input=input_data)

        self.assertTrue(res.ok)
        self.assertEqual(res.object.tags.count(), 1)
        self.assertTrue(res.object.tags.filter(name="Tag2").exists())

    def test_update_m2m_create_new(self):
        """Test updating Post M2M by creating new tags inline."""
        cat = Category.objects.create(name="Cat")
        post = Post.objects.create(title="My Post", category=cat)

        mutation = self.mut_gen.generate_update_mutation(Post)

        input_data = {"tags": {"create": [{"name": "NewTag1"}, {"name": "NewTag2"}]}}

        info = create_info(self.user)
        res = mutation.mutate(None, info, id=str(post.id), input=input_data)

        self.assertTrue(res.ok)
        self.assertEqual(res.object.tags.count(), 2)
        self.assertTrue(res.object.tags.filter(name="NewTag1").exists())
        self.assertTrue(res.object.tags.filter(name="NewTag2").exists())

    def test_update_reverse_relation_connect(self):
        """Test updating Category by connecting existing Posts."""
        cat = Category.objects.create(name="Cat")
        cat2 = Category.objects.create(name="Cat2")
        post = Post.objects.create(title="Post", category=cat2)

        mutation = self.mut_gen.generate_update_mutation(Category)

        # Connect post to this category
        input_data = {"posts": {"connect": [str(post.id)]}}

        info = create_info(self.user)
        res = mutation.mutate(None, info, id=str(cat.id), input=input_data)

        self.assertTrue(res.ok)
        post.refresh_from_db()
        self.assertEqual(post.category.id, cat.id)

    def test_fk_connect_invalid_id_returns_error(self):
        """Test that connecting to non-existent ID returns validation error."""
        mutation = self.mut_gen.generate_create_mutation(Product)

        input_data = {
            "name": "Product",
            "price": 10.0,
            "category": {"connect": "99999"},  # Non-existent ID
        }

        info = create_info(self.user)
        res = mutation.mutate(None, info, input=input_data)

        self.assertFalse(res.ok)
        self.assertIsNotNone(res.errors)


@pytest.mark.integration
class TestUnifiedMutationValidation(TestCase):
    """Tests for validation of unified relation operations."""

    def setUp(self):
        from django.contrib.auth.models import User
        from rail_django.generators.types import TypeGenerator
        from rail_django.generators.mutations import MutationGenerator
        from rail_django.core.settings import MutationGeneratorSettings

        self.user = User.objects.create_user("testuser2", "test2@example.com", "pass")
        grant_permissions(
            self.user,
            {
                Category: ["add_category", "change_category"],
                Product: ["add_product", "change_product"],
                Post: ["add_post", "change_post"],
                Tag: ["add_tag", "change_tag"],
            },
        )

        self.settings = MutationGeneratorSettings()
        self.type_gen = TypeGenerator(mutation_settings=self.settings)
        self.mut_gen = MutationGenerator(self.type_gen, settings=self.settings)

    def test_singular_relation_multiple_ops_error(self):
        """Test that providing multiple operations for FK raises error."""
        from rail_django.generators.pipeline.utils import process_relation_operations
        from django.core.exceptions import ValidationError

        # For FK, only one of connect/create/update should be allowed
        input_data = {
            "name": "Test",
            "category": {
                "connect": "1",
                "create": {"name": "New"},  # Should not be allowed with connect
            },
        }

        with self.assertRaises(ValidationError) as ctx:
            process_relation_operations(input_data, Product)

        self.assertIn("category", str(ctx.exception))

    def test_m2m_set_with_connect_error(self):
        """Test that 'set' combined with 'connect' raises error for M2M."""
        from rail_django.generators.pipeline.utils import process_relation_operations
        from django.core.exceptions import ValidationError

        input_data = {
            "title": "Test",
            "tags": {
                "set": ["1", "2"],
                "connect": ["3"],  # Should not be allowed with set
            },
        }

        # Need a mock category for Post
        cat = Category.objects.create(name="Test Cat")

        with self.assertRaises(ValidationError) as ctx:
            process_relation_operations(input_data, Post)

        self.assertIn("tags", str(ctx.exception))

