"""
Constants and mappings for type generation.
"""

from datetime import date
import graphene
from django.db import models


# Mapping of Django field types to GraphQL scalar types
FIELD_TYPE_MAP = {
    models.AutoField: graphene.ID,
    models.BigAutoField: graphene.ID,
    models.SmallAutoField: graphene.ID,
    models.BigIntegerField: graphene.Int,
    models.BooleanField: graphene.Boolean,
    models.CharField: graphene.String,
    models.DateField: graphene.Date,
    models.DateTimeField: graphene.DateTime,
    models.DecimalField: graphene.Decimal,
    models.EmailField: graphene.String,
    models.FileField: graphene.String,
    models.FilePathField: graphene.String,
    models.FloatField: graphene.Float,
    models.GenericIPAddressField: graphene.String,
    models.ImageField: graphene.String,
    models.IntegerField: graphene.Int,
    models.JSONField: graphene.JSONString,
    models.PositiveBigIntegerField: graphene.Int,
    models.PositiveIntegerField: graphene.Int,
    models.PositiveSmallIntegerField: graphene.Int,
    models.SlugField: graphene.String,
    models.SmallIntegerField: graphene.Int,
    models.TextField: graphene.String,
    models.BinaryField: graphene.String,
    models.DurationField: graphene.String,
    models.TimeField: graphene.Time,
    models.URLField: graphene.String,
    models.UUIDField: graphene.UUID,
}

# Mapping of Python types to GraphQL scalar types for @property methods
PYTHON_TYPE_MAP = {
    str: graphene.String,
    int: graphene.Int,
    float: graphene.Float,
    bool: graphene.Boolean,
    list: graphene.List,
    dict: graphene.JSONString,
    date: graphene.Date,
}
