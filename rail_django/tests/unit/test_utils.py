"""
Unit tests for Rail Django utility functions.
"""

from datetime import date, datetime, timezone
import pytest
from rail_django.utils.datetime_utils import (
    parse_iso_datetime,
    format_iso_datetime,
    parse_date,
    coerce_date,
    now_utc,
    format_date
)
from rail_django.utils.normalization import (
    normalize_list,
    normalize_string_list,
    normalize_accessor,
    normalize_header_key,
    normalize_legacy_config,
    normalize_model_label,
    normalize_dict_keys
)

pytestmark = pytest.mark.unit

class TestDateTimeUtils:
    def test_parse_iso_datetime(self):
        # UTC with Z
        dt = parse_iso_datetime("2024-01-15T10:30:00Z")
        assert dt == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        
        # Offset
        dt = parse_iso_datetime("2024-01-15T10:30:00+01:00")
        assert dt.hour == 10
        assert dt.utcoffset().total_seconds() == 3600
        
        # Invalid
        assert parse_iso_datetime("invalid") is None
        assert parse_iso_datetime(None) is None

    def test_format_iso_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30)
        assert format_iso_datetime(dt) == "2024-01-15T10:30:00"

    def test_parse_date(self):
        assert parse_date("2024-01-15") == date(2024, 1, 15)
        assert parse_date(datetime(2024, 1, 15, 10, 30)) == date(2024, 1, 15)
        assert parse_date(date(2024, 1, 15)) == date(2024, 1, 15)
        assert parse_date(None) is None
        assert parse_date("invalid") is None

    def test_now_utc(self):
        dt = now_utc()
        assert dt.tzinfo == timezone.utc

class TestNormalizationUtils:
    def test_normalize_list(self):
        assert normalize_list(["Product", "ORDER", None]) == ["product", "order"]
        assert normalize_list([]) == []

    def test_normalize_string_list(self):
        assert normalize_string_list(["Product", 123, None]) == ["Product", "123"]

    def test_normalize_accessor(self):
        assert normalize_accessor("  user__profile__name  ") == "user__profile__name"
        assert normalize_accessor("user  __  name") == "user__name"

    def test_normalize_header_key(self):
        assert normalize_header_key("X-Tenant-ID") == "x_tenant_id"
        assert normalize_header_key("Authorization") == "authorization"

    def test_normalize_legacy_config(self):
        legacy = {
            "GRAPHQL": {"path": "/gql"},
            "AUTO_CAMELCASE": True
        }
        normalized = normalize_legacy_config(legacy)
        assert "SCHEMA" in normalized
        assert "auto_camelcase" in normalized
        assert normalized["SCHEMA"] == {"path": "/gql"}
        assert normalized["auto_camelcase"] is True

    def test_normalize_model_label(self):
        assert normalize_model_label("myapp.MyModel") == "myapp.MyModel"
        
        class MockMeta:
            app_label = "testapp"
            object_name = "TestModel"
        
        class MockModel:
            _meta = MockMeta()
            
        assert normalize_model_label(MockModel) == "testapp.TestModel"

    def test_normalize_dict_keys(self):
        data = {"FirstName": "John", "LAST_NAME": "Doe"}
        assert normalize_dict_keys(data) == {"firstname": "John", "last_name": "Doe"}
        assert normalize_dict_keys(data, lowercase=False) == data
