import os
import pytest
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from rail_django.core.schema.auto_generator import AutoSchemaGenerator
from tests.models import TestCompany
# We don't need to import graphene_settings here anymore if we patch it in the command

@pytest.mark.django_db
def test_eject_schema_command(tmp_path):
    """Test the eject_schema management command."""
    
    # Generate a real schema using the AutoGenerator
    generator = AutoSchemaGenerator()
    schema = generator.get_schema([TestCompany])
    
    # Patch the graphene_settings imported in the command file
    with patch("rail_django.management.commands.eject_schema.graphene_settings") as mock_settings:
        mock_settings.SCHEMA = schema
        
        out = StringIO()
        call_command("eject_schema", stdout=out)
        output = out.getvalue()
        
        # Basic check that it looks like SDL
        assert "type Query" in output
        # assert "schema {" in output # SDL might omit this if defaults are used
        assert "TestCompanyType" in output or "TestCompany" in output

@pytest.mark.django_db
def test_eject_schema_json(tmp_path):
    """Test JSON output."""
    generator = AutoSchemaGenerator()
    schema = generator.get_schema([TestCompany])
    
    with patch("rail_django.management.commands.eject_schema.graphene_settings") as mock_settings:
        mock_settings.SCHEMA = schema

        out = StringIO()
        call_command("eject_schema", json=True, stdout=out)
        output = out.getvalue()
        
        import json
        data = json.loads(output)
        assert "__schema" in data
