import pytest
from graphene_django import DjangoObjectType
from rail_django.core.schema.auto_generator import AutoSchemaGenerator
from tests.models import TestGeneratedModel

@pytest.mark.django_db
def test_auto_schema_generator_with_generated_field():
    """
    Test that AutoSchemaGenerator can handle Django 5.0 GeneratedField.
    """
    generator = AutoSchemaGenerator()
    
    # This should not raise an exception
    schema = generator.get_schema([TestGeneratedModel])
    
    # Verify the schema has the generated field
    query = """
    query {
        __type(name: "TestGeneratedModelType") {
            fields {
                name
            }
        }
    }
    """
    result = schema.execute(query)
    assert result.errors is None
    
    fields = [f['name'] for f in result.data['__type']['fields']]
    assert 'area' in fields
    assert 'side' in fields
