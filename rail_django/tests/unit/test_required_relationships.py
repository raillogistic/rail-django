"""
Tests for required relationship fields in GraphQL input types.

This module tests that relationship fields with blank=False are correctly
marked as required (NonNull) in GraphQL input types for create mutations.
"""

import graphene
import pytest
from django.contrib.auth.models import User
from django.db import models
from django.test import TestCase
from examples.basic_usage import Category, Post
from rail_django.generators.types import TypeGenerator


class TestRequiredRelationships(TestCase):
    """Tests for required relationship fields in input types."""

    def setUp(self):
        """Set up test fixtures."""
        self.type_generator = TypeGenerator()

    def test_foreign_key_required_field_in_create_input(self):
        """Test that ForeignKey fields with blank=False are required in create input."""
        # Generate create input type for Post model
        create_input = self.type_generator.generate_input_type(Post, "create")

        # Get the fields from the input type
        fields = create_input._meta.fields

        # Check that the ForeignKey field exists
        self.assertIn("categorie_article", fields)

        # Check that the field is required (NonNull)
        field_type = fields["categorie_article"]
        self.assertIsInstance(field_type, graphene.InputField)

        # The field should be NonNull since Post.categorie_article has blank=False by default
        # and it's a required field for creation
        self.assertTrue(hasattr(field_type._type, "_of_type"))
        self.assertEqual(field_type._type.__class__.__name__, "NonNull")

    def test_foreign_key_optional_field_in_update_input(self):
        """Test that ForeignKey fields are optional in update input."""
        # Generate update input type for Post model
        update_input = self.type_generator.generate_input_type(
            Post, "update", partial=True
        )

        # Get the fields from the input type
        fields = update_input._meta.fields

        # Check that the ForeignKey field exists
        self.assertIn("categorie_article", fields)

        # Check that the field is optional (not NonNull)
        field_type = fields["categorie_article"]
        self.assertIsInstance(field_type, graphene.InputField)

        # The field should be optional for updates (partial=True)
        self.assertFalse(hasattr(field_type._type, "_of_type"))

    def test_model_with_blank_true_foreign_key(self):
        """Test that ForeignKey fields with blank=True are optional."""

        # Create a test model with blank=True ForeignKey
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            optional_category = models.ForeignKey(
                Category, on_delete=models.CASCADE, blank=True, null=True
            )

            class Meta:
                app_label = "test_app"

        # Generate create input type for the test model
        create_input = self.type_generator.generate_input_type(TestModel, "create")

        # Get the fields from the input type
        fields = create_input._meta.fields

        # Check that the optional ForeignKey field exists
        self.assertIn("optional_category", fields)

        # Check that the field is optional (not NonNull)
        field_type = fields["optional_category"]
        self.assertIsInstance(field_type, graphene.InputField)

        # The field should be optional since it has blank=True
        self.assertFalse(hasattr(field_type._type, "_of_type"))

    def test_one_to_one_required_field(self):
        """Test that OneToOneField fields with blank=False are required."""

        # Create a test model with OneToOneField
        class TestProfile(models.Model):
            user = models.OneToOneField(User, on_delete=models.CASCADE)
            bio = models.TextField()

            class Meta:
                app_label = "test_app"

        # Generate create input type for the test model
        create_input = self.type_generator.generate_input_type(TestProfile, "create")

        # Get the fields from the input type
        fields = create_input._meta.fields

        # Check that the OneToOne field exists
        self.assertIn("user", fields)

        # Check that the field is required (NonNull)
        field_type = fields["user"]
        self.assertIsInstance(field_type, graphene.InputField)

        # The field should be NonNull since it has blank=False by default
        self.assertTrue(hasattr(field_type._type, "_of_type"))
        self.assertEqual(field_type._type.__class__.__name__, "NonNull")

    def test_many_to_many_field_requirements(self):
        """Test that ManyToManyField fields are handled correctly."""

        # Create a test model with ManyToManyField
        class TestArticle(models.Model):
            title = models.CharField(max_length=100)
            tags = models.ManyToManyField(Category)

            class Meta:
                app_label = "test_app"

        # Generate create input type for the test model
        create_input = self.type_generator.generate_input_type(TestArticle, "create")

        # Get the fields from the input type
        fields = create_input._meta.fields

        # Check that the ManyToMany field exists
        self.assertIn("tags", fields)

        # Check the field type
        field_type = fields["tags"]
        self.assertIsInstance(field_type, graphene.InputField)

        # ManyToMany fields should be optional by default for create mutations
        # since they can be added after object creation
        self.assertFalse(hasattr(field_type._type, "_of_type"))


@pytest.mark.unit
def test_required_relationship_field_behavior():
    """Integration test for required relationship fields."""
    type_generator = TypeGenerator()

    # Test with Post model that has required ForeignKey to Category
    create_input = type_generator.generate_input_type(Post, "create")

    # Verify the categorie_article field is required
    fields = create_input._meta.fields
    assert "categorie_article" in fields

    field_type = fields["categorie_article"]

    # The field should be NonNull (required) for create mutations
    # when the Django field has blank=False (default)
    assert hasattr(field_type._type, "_of_type")
    assert field_type._type.__class__.__name__ == "NonNull"
