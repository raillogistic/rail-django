import pytest
from django.db import models

from rail_django.extensions.form.utils.type_mapping import (
    map_field_input_type,
    map_graphql_type,
    map_python_type,
)
from tests.models import TestGeneratedModel

pytestmark = pytest.mark.unit


def test_map_field_input_type_supports_common_numeric_and_ip_fields():
    assert map_field_input_type(models.PositiveBigIntegerField()) == "NUMBER"
    assert map_field_input_type(models.BigAutoField()) == "NUMBER"
    assert map_field_input_type(models.GenericIPAddressField()) == "TEXT"


def test_map_graphql_type_supports_common_numeric_and_ip_fields():
    assert map_graphql_type(models.PositiveBigIntegerField()) == "Int"
    assert map_graphql_type(models.BigAutoField()) == "ID"
    assert map_graphql_type(models.GenericIPAddressField()) == "String"


def test_map_python_type_supports_common_numeric_and_ip_fields():
    assert map_python_type(models.PositiveBigIntegerField()) == "int"
    assert map_python_type(models.BigAutoField()) == "int"
    assert map_python_type(models.GenericIPAddressField()) == "str"


def test_generated_field_uses_output_field_mapping():
    generated = TestGeneratedModel._meta.get_field("area")
    assert map_field_input_type(generated) == "NUMBER"
    assert map_graphql_type(generated) == "Int"
    assert map_python_type(generated) == "int"
