
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.test import TestCase
from rail_django.extensions.metadata_v2.field_extractor import FieldExtractorMixin

class ValidatorTestModel(models.Model):
    age = models.IntegerField(validators=[MinValueValidator(18), MaxValueValidator(100)])
    code = models.CharField(max_length=10, validators=[RegexValidator(r'^[A-Z]+$', 'Only uppercase', 'invalid')])

    class Meta:
        app_label = 'test_metadata_v2_validators'

class TestValidatorExtraction(TestCase):
    def test_extract_validators(self):
        extractor = FieldExtractorMixin()
        extractor._map_to_graphql_type = lambda t, f: "String"
        extractor._get_python_type = lambda f: "str"

        # Extract age field
        age_field = ValidatorTestModel._meta.get_field('age')

        # We'll use the mixin but we need to patch the helper methods it uses or mock them if they are imported
        # _classify_field is imported in field_extractor.py

        from unittest.mock import patch
        with patch('rail_django.extensions.metadata_v2.field_extractor._classify_field') as mock_classify:
            mock_classify.return_value = {
                "is_primary_key": False,
                "is_indexed": False,
                "is_relation": False,
                "is_computed": False,
                "is_file": False,
                "is_image": False,
                "is_json": False,
                "is_date": False,
                "is_datetime": False,
                "is_numeric": True,
                "is_boolean": False,
                "is_text": False,
                "is_rich_text": False,
                "is_fsm_field": False,
            }

            schema = extractor._extract_field(ValidatorTestModel, age_field, user=None)

            self.assertIsNotNone(schema)
            validators = schema['validators']
            self.assertEqual(len(validators), 2)

            min_val = next(v for v in validators if v['type'] == 'MinValueValidator')
            self.assertEqual(min_val['params']['limit_value'], 18)

            max_val = next(v for v in validators if v['type'] == 'MaxValueValidator')
            self.assertEqual(max_val['params']['limit_value'], 100)

    def test_extract_regex_validator(self):
        extractor = FieldExtractorMixin()
        extractor._map_to_graphql_type = lambda t, f: "String"
        extractor._get_python_type = lambda f: "str"

        code_field = ValidatorTestModel._meta.get_field('code')

        from unittest.mock import patch
        with patch('rail_django.extensions.metadata_v2.field_extractor._classify_field') as mock_classify:
            mock_classify.return_value = {
                "is_primary_key": False,
                "is_indexed": False,
                "is_relation": False,
                "is_computed": False,
                "is_file": False,
                "is_image": False,
                "is_json": False,
                "is_date": False,
                "is_datetime": False,
                "is_numeric": False,
                "is_boolean": False,
                "is_text": True,
                "is_rich_text": False,
                "is_fsm_field": False,
            }

            schema = extractor._extract_field(ValidatorTestModel, code_field, user=None)

            self.assertIsNotNone(schema)
            validators = schema['validators']
            # CharField with max_length adds a MaxLengthValidator automatically
            # So we expect RegexValidator and MaxLengthValidator
            self.assertGreaterEqual(len(validators), 1)

            regex_val = next((v for v in validators if v['type'] == 'RegexValidator'), None)
            self.assertIsNotNone(regex_val)
            self.assertEqual(regex_val['params']['pattern'], r'^[A-Z]+$')
            self.assertEqual(regex_val['message'], 'Only uppercase')
            self.assertEqual(regex_val['params']['code'], 'invalid')
