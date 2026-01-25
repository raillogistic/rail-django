
from django.db import models
from django.test import TestCase
from django.utils.translation import activate, deactivate
from rail_django.extensions.metadata_v2.filter_extractor import FilterExtractorMixin
from unittest.mock import MagicMock, patch
import graphene

class DynamicFilterTestModel(models.Model):
    name = models.CharField(max_length=100)
    age = models.IntegerField()
    is_active = models.BooleanField()
    created_at = models.DateTimeField()

    class Meta:
        app_label = 'test_metadata_v2_dynamic'

class TestDynamicFilteringMetadata(TestCase):
    def setUp(self):
        self.extractor = FilterExtractorMixin()
        self.extractor.schema_name = "default"

    def tearDown(self):
        deactivate()

    def test_base_type_extraction(self):
        """Test that base_type is correctly inferred from model fields."""
        model = DynamicFilterTestModel

        # Helper to create mock input field
        def create_mock_input(field_name, op_name="eq"):
            input_field = MagicMock()
            input_type = MagicMock()
            del input_type.of_type # Prevent loop
            input_type._meta.name = f"{field_name}FilterInput"

            # Create operator field
            op_field = MagicMock()
            op_field.type = graphene.String # Default

            input_type._meta.fields = {op_name: op_field}
            input_field.type = input_type
            return input_field

        # Test String (name)
        with patch('graphene.utils.str_converters.to_camel_case', side_effect=lambda x: x):
            input_field = create_mock_input("name")
            result = self.extractor._analyze_filter_field(model, "name", input_field)
            self.assertEqual(result['base_type'], "String")

        # Test Number (age)
        with patch('graphene.utils.str_converters.to_camel_case', side_effect=lambda x: x):
            input_field = create_mock_input("age", "gt")
            result = self.extractor._analyze_filter_field(model, "age", input_field)
            self.assertEqual(result['base_type'], "Number")

        # Test Boolean (is_active)
        with patch('graphene.utils.str_converters.to_camel_case', side_effect=lambda x: x):
            input_field = create_mock_input("is_active")
            result = self.extractor._analyze_filter_field(model, "is_active", input_field)
            self.assertEqual(result['base_type'], "Boolean")

        # Test Date (created_at)
        with patch('graphene.utils.str_converters.to_camel_case', side_effect=lambda x: x):
            input_field = create_mock_input("created_at")
            result = self.extractor._analyze_filter_field(model, "created_at", input_field)
            self.assertEqual(result['base_type'], "Date")

    def test_operator_labels(self):
        """Test that operator labels are localized."""
        model = DynamicFilterTestModel
        activate('en')

        input_field = MagicMock()
        input_type = MagicMock()
        del input_type.of_type
        input_type._meta.name = "StringFilterInput"

        # Add various operators
        op_eq = MagicMock(); op_eq.type = graphene.String
        op_contains = MagicMock(); op_contains.type = graphene.String

        input_type._meta.fields = {
            "eq": op_eq,
            "contains": op_contains
        }
        input_field.type = input_type

        with patch('graphene.utils.str_converters.to_camel_case', side_effect=lambda x: x):
            result = self.extractor._analyze_filter_field(model, "name", input_field)

            options = result['options']
            eq_opt = next(o for o in options if o['lookup'] == 'eq')
            contains_opt = next(o for o in options if o['lookup'] == 'contains')

            self.assertEqual(eq_opt['label'], "Equals")
            self.assertEqual(contains_opt['label'], "Contains")

    def test_unknown_operator_fallback(self):
        """Test fallback for unknown operators."""
        model = DynamicFilterTestModel

        input_field = MagicMock()
        input_type = MagicMock()
        del input_type.of_type
        input_type._meta.name = "StringFilterInput"

        op_custom = MagicMock(); op_custom.type = graphene.String
        input_type._meta.fields = {"custom_op": op_custom}
        input_field.type = input_type

        with patch('graphene.utils.str_converters.to_camel_case', side_effect=lambda x: x):
            result = self.extractor._analyze_filter_field(model, "name", input_field)

            custom_opt = result['options'][0]
            self.assertEqual(custom_opt['lookup'], "custom_op")
            self.assertEqual(custom_opt['label'], "custom_op") # Fallback to name
